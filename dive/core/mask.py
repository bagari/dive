import vtk
import numpy as np
import nibabel as nib
from fury import actor
from scipy.ndimage import map_coordinates
from nibabel.orientations import apply_orientation, io_orientation, ornt_transform
from dive.utils.color import get_palette
from meta.io.transform import load_transformation


def _reorient(data, from_affine, to_affine):
    """Match data orientation to reference affine."""
    from_ornt = io_orientation(from_affine)
    to_ornt = io_orientation(to_affine)
    if np.array_equal(from_ornt, to_ornt):
        return data
    xform = ornt_transform(from_ornt, to_ornt)
    return apply_orientation(data, xform)


def _warp_mask_dsi_studio(mask_img, warp_img, ref_img):
    """Resample a label mask onto the reference grid using a DSI-Studio warp.
    """
    data = np.asanyarray(mask_img.dataobj)
    mask_dtype = mask_img.get_data_dtype()

    warp_data = warp_img.get_fdata(dtype=np.float32)
    if warp_data.ndim == 5:
        if warp_data.shape[3] != 1:
            raise ValueError(f"Expected 5D warp shape (X, Y, Z, 1, 3), got {warp_data.shape}.")
        warp_data = warp_data[:, :, :, 0, :]
    if warp_data.ndim != 4 or warp_data.shape[-1] != 3:
        raise ValueError(f"Expected warp shape (X, Y, Z, 3), got {warp_data.shape}.")

    if warp_img.shape[:3] != ref_img.shape[:3]:
        raise ValueError(
            f"Warp grid {warp_img.shape[:3]} must match reference grid {ref_img.shape[:3]}. "
            f"Use 1InverseWarp for subject→MNI or 1Warp for MNI→subject."
        )

    data = _reorient(data, mask_img.affine, warp_img.affine)
    coords = np.stack(
        [warp_data[..., 0], warp_data[..., 1], warp_data[..., 2]], axis=0
    ).astype(np.float32)
    warped = map_coordinates(data, coords, order=0, mode="constant", cval=0, prefilter=False)
    warped = _reorient(warped, warp_img.affine, ref_img.affine)

    out_data = np.asarray(warped, dtype=mask_dtype)
    new_header = ref_img.header.copy()
    new_header.set_data_dtype(mask_dtype)
    return nib.Nifti1Image(out_data, ref_img.affine, new_header)


def build_actor_mask(
    mask_img,
    color=None,
    colormap=None,
    opacity=1.0,
    transform=None,
    inverse=False,
    warp=None,
    warp_source="dsi_studio",
    reference=None,
):
    """Build a VTK actor or assembly for a single-label or multi-label NIfTI mask.

    Parameters
    ----------
    mask_img : nibabel.Nifti1Image
        Labeled mask image.
    color : tuple of float, optional
        RGB color (0–1) for a single-label mask. Ignored for multi-label masks.
    colormap : list of RGB tuples, optional
        Per-ROI colors for multi-label masks.
    opacity : float
        Surface opacity in [0, 1].
    transform : path-like, optional
        Path to a linear transformation file.
    inverse : bool
        If True, invert ``transform`` before applying.
    warp : path-like or nibabel.Nifti1Image, optional
        Non-linear warp field. Used only when ``warp_source='dsi_studio'``.
    warp_source : {'dsi_studio', 'ants'}
        Warp convention. ANTs warps are not yet supported for masks
    reference : path-like or nibabel.Nifti1Image, optional
        Reference image whose grid/affine defines the output space. Required
        when the warp is applied for DSI-Studio.

    Returns
    -------
    vtkActor or vtkAssembly
        Single actor for single-label masks; assembly of per-ROI actors for multi-label masks.
    """
    use_warp = warp is not None and warp_source == "dsi_studio"

    if warp is not None and warp_source not in ("dsi_studio", "ants"):
        raise ValueError(f"Unknown warp_source: {warp_source!r}.")

    if use_warp:
        if reference is None:
            raise ValueError("'reference' is required when applying a warp.")
        warp_img = warp if isinstance(warp, nib.Nifti1Image) else nib.load(warp)
        ref_img = reference if isinstance(reference, nib.Nifti1Image) else nib.load(reference)
        mask_img = _warp_mask_dsi_studio(mask_img, warp_img, ref_img)
        affine = mask_img.affine

    else:
        # Linear (no warp, or ANTs warp not supported for masks now).
        if transform is not None:
            T = load_transformation(transform)
            if inverse:
                T = np.linalg.inv(T)
            affine = T @ mask_img.affine
        else:
            if inverse:
                raise ValueError("Requires a '--transform' to invert.")
            affine = mask_img.affine

    data = mask_img.get_fdata()
    nonzero = np.unique(data[data != 0])

    if len(nonzero) == 0:
        raise ValueError("No labels found (empty mask).")

    # Multi-label mask: create a contour actor for each label and combine in an assembly.
    if len(nonzero) > 1:
        assembly = vtk.vtkAssembly()
        for i, roi in enumerate(nonzero):
            if colormap is not None and i < len(colormap):
                roi_color = list(colormap[i])
            else:
                palette = get_palette(int(roi) + 1)
                roi_color = list(palette[int(roi) % len(palette)])
            assembly.AddPart(
                actor.contour_from_roi((data == roi).astype(np.uint8),
                    affine=affine, color=roi_color, opacity=opacity)
            )
        return assembly

    # Single-label mask
    return actor.contour_from_roi((data == nonzero[0]).astype(np.uint8),
        affine=affine, color=color, opacity=opacity)
