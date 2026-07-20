import os
import logging
import numpy as np
import nibabel as nib
from nibabel.streamlines import ArraySequence

from meta.io.streamline import read_streamlines
from meta.transforms.tractogram import transform_tractogram
from dive.core.mesh import load_mesh
from dive.core.mask import build_actor_mask
from dive.core.tract import tract_with_colormap, tract_single_color, tract_direction_color, tract_segmented_color
from dive.utils.color import assign_colors, get_color, get_palette

log = logging.getLogger(__name__)


def _has_mask_overlap(streamlines, mask_img, min_fraction = 0.5):
    """
    Return True only if at least `min_fraction` of streamline points fall inside
    a non-zero mask label. A low fraction means the mask doesn't cover this tract
    meaningfully, so coloring it would produce a mostly-black actor.
    """
    inv_affine = np.linalg.inv(mask_img.affine)
    mask_data = mask_img.get_fdata()
    shape = np.array(mask_data.shape)
    pts = np.vstack(list(streamlines))
    vox = np.round(nib.affines.apply_affine(inv_affine, pts)).astype(int)
    valid = np.all((vox >= 0) & (vox < shape), axis=1)
    if not np.any(valid):
        return False
    overlap_fraction = float(np.mean(mask_data[vox[valid, 0], vox[valid, 1], vox[valid, 2]] > 0))
    log.debug("mask overlap fraction: %.3f", overlap_fraction)
    return overlap_fraction >= min_fraction


def load_scene_objects(
    masks=None, tracts=None, meshes=None,
    mask_colors=None, tract_colors=None, mesh_colors=None,
    mask_opacity=None, tract_opacity=None, mesh_opacity=None,
    stats_csv=None, group_stat=None, colormap='RdBu', value_range=None,
    threshold=0.05, log_p_value=False, tract_width=1,
    segmentation_method=None, num_segments=None, s_len=None,
    transform=None, inverse=False, warp=None, warp_ref=None, warp_source=None,
    warp_first=False, trim_endpoints=True, output=None):
    """
    Load and color masks, tracts, and meshes.
    Returns {display_name: actor} — caller is responsible for adding to scene.
    """
    
    masks = list(masks or [])
    tracts = list(tracts or [])
    meshes = list(meshes or [])
    mask_colors = list(mask_colors or [])
    tract_colors = list(tract_colors or [])
    mesh_colors = list(mesh_colors or [])
    mask_opacity = list(mask_opacity or [])
    tract_opacity = list(tract_opacity or [])
    mesh_opacity = list(mesh_opacity or [])
    stats_csv = list(stats_csv or [])

    rois = {}
    multilabel_mask_img = None
    multilabel_color_map = None
    color_map = []

    def _opacity(lst, i, default=1.0):
        return lst[i] if i < len(lst) else default

    # --- CSV colors (one color_map per --stats_csv, paired by index) ---
    color_maps = []
    if stats_csv:
        color_maps = [
            assign_colors(
                stats_csv=csv_path,
                cmap_name=colormap,
                range_value=value_range,
                log_p_value=log_p_value,
                threshold=threshold,
                output=output,
                group_stat=group_stat,
            )
            for csv_path in stats_csv
        ]

    # --- Masks ---
    for i, path in enumerate(masks):
        mask_img = nib.load(path)
        name = os.path.basename(path)
        opacity = _opacity(mask_opacity, i)
        color = mask_colors[i] if i < len(mask_colors) else None
        color_map = color_maps[i] if i < len(color_maps) else []

        if len(np.unique(mask_img.get_fdata())) > 2:
            if multilabel_mask_img is None:
                multilabel_mask_img = mask_img
                multilabel_color_map = color_map
            actor = build_actor_mask(
                mask_img=mask_img, colormap=color_map or None, opacity=opacity,
                transform=transform, inverse=inverse, warp=warp,
                warp_source=warp_source, reference=warp_ref,
            )
        else:
            actor = build_actor_mask(
                mask_img=mask_img, color=color or get_color(i), opacity=opacity,
                transform=transform, inverse=inverse, warp=warp,
                warp_source=warp_source, reference=warp_ref,
            )
        rois[name] = actor

    # --- Tracts ---
    for i, tract in enumerate(tracts):
        if transform is not None or warp is not None:
            streamlines, groups, affine, dimension = transform_tractogram(
                tractogram=tract, transform=transform, warp=warp, reference=warp_ref,
                inverse=inverse, warp_first=warp_first, warp_source=warp_source,
                trim_endpoints=trim_endpoints,
            )
        else:
            streamlines, groups, affine, dimension = read_streamlines(tract)

        name = os.path.basename(tract)
        opacity = _opacity(tract_opacity, i)
        color = tract_colors[i] if i < len(tract_colors) else None
        color_map = color_maps[i] if i < len(color_maps) else []

        if groups:
            # TRX groups: top-level streamlines may be None, so always check groups first
            palette = get_palette(len(groups))
            colors = color_map or [palette[k % len(palette)] for k in range(len(groups))]
            for idx, (group_name, indices) in enumerate(groups.items()):
                group_sl = ArraySequence([streamlines[j] for j in indices])
                rois[group_name] = tract_single_color(
                    bundle=group_sl, color=colors[idx], line_width=tract_width,
                )
            continue

        if multilabel_mask_img is not None:
            if _has_mask_overlap(streamlines, multilabel_mask_img):
                actor = tract_with_colormap(
                    bundle=streamlines, mask=multilabel_mask_img, colors_from_csv=multilabel_color_map,
                    line_width=tract_width, opacity=opacity,
                )
            else:
                log.warning("%s: no spatial overlap with the multi-label mask "
                            "→ falling back to directional coloring", name)
                actor = tract_direction_color(bundle=streamlines, line_width=tract_width, opacity=opacity)

        elif color:
            actor = tract_single_color(
                bundle=streamlines, color=color, line_width=tract_width, opacity=opacity,
            )
        elif segmentation_method in ("centerline", "hyperplane", "linear", "spline"):
            actor = tract_segmented_color(
                bundle=streamlines, method=segmentation_method,
                num_segments=num_segments, s_len=s_len,
                line_width=tract_width,
                opacity=opacity, colors_from_csv=color_map,
                bundle_shape=dimension, affine=affine,
            )
        else:
            actor = tract_direction_color(
                bundle=streamlines, line_width=tract_width, opacity=opacity,
            )

        rois[name] = actor

    # --- Meshes ---
    for i, path in enumerate(meshes):
        name = os.path.basename(path)
        opacity = _opacity(mesh_opacity, i)
        color = mesh_colors[i] if i < len(mesh_colors) else get_color(i)
        rois[name] = load_mesh(polydata_path=path, color=color, opacity=opacity)

    return rois
