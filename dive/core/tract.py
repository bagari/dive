import numpy as np
import logging
import nibabel as nib
from fury import actor, colormap
from scipy.spatial import cKDTree
from scipy.interpolate import splprep, splev
from nibabel.streamlines.array_sequence import ArraySequence
from dipy.tracking.utils import length
from dipy.tracking.streamline import set_number_of_points, Streamlines
from dipy.segment.metric import AveragePointwiseEuclideanMetric
from dipy.segment.clustering import QuickBundles

from dive.utils.color import get_palette
from dive.core.segments import get_alignment
from meta.core.segments import segment_bundle

log = logging.getLogger(__name__)

## density_map: expects voxel-space coordinates
def bundle_density(streamlines, ref_shape, ref_affine):
    from dipy.tracking import utils

    # sls world-coordinates → voxel coordinates
    inv_aff = np.linalg.inv(ref_affine)
    voxel_sls = [nib.affines.apply_affine(inv_aff, sl) for sl in streamlines]

    # Clip negative or out-of-bound voxel coords:
    voxel_sls = [np.clip(sl, 0, np.array(ref_shape) - 1) for sl in voxel_sls]

    # Upsample streamlines:
    max_seq_len = abs(ref_affine[0, 0] / 4)
    voxel_sls = list(utils.subsegment(voxel_sls, max_seq_len))

    ## Create density map and then binarize it.
    dm = utils.density_map(voxel_sls, vol_dims=ref_shape, affine=np.eye(4))
    dm_binary = (dm > 0).astype("uint8")
    return nib.Nifti1Image(dm_binary, ref_affine)


def _normalize_bundle(bundle):
    """Convert any streamline container to a list of valid (N, 3) float32 arrays.
    Streamlines with 2 points are dropped.
    """
    raw = bundle.to_list() if hasattr(bundle, 'to_list') else list(bundle)
    return [
        np.asarray(sl, dtype=np.float32)
        for sl in raw
        if np.asarray(sl).ndim == 2 and np.asarray(sl).shape[1] == 3 and len(sl) >= 2
    ]

def _make_actor(bundle, colors, tw, opacity):
    """Return a FURY line actor with the given per-point colors and opacity."""
    stream_actor = actor.line(bundle, fake_tube=True, colors=colors, linewidth=tw)
    stream_actor.GetProperty().SetOpacity(opacity)
    return stream_actor


def tract_with_colormap(bundle, mask, colors_from_csv, line_width=1, opacity=1.0):
    """Color each streamline point by its mask label using a CSV colormap.

    Parameters
    ----------
    bundle : streamline container
        Streamlines to render.
    mask : nibabel.Nifti1Image
        Labeled mask used to assign colors per point.
    colors_from_csv : list of RGB tuples or None
        Per-label colors. Auto-generated via distinctipy if None or empty.
    line_width : int
        Line width.
    opacity : float
        Actor opacity in [0, 1].

    Returns
    -------
    vtkActor
    """
    pts = np.vstack(list(bundle)) # (N, 3) world coords
    inv_affine = np.linalg.inv(mask.affine)
    voxels = np.round(nib.affines.apply_affine(inv_affine, pts)).astype(int)

    data = mask.get_fdata()
    shape = np.asarray(data.shape)
    in_bounds = np.all((voxels >= 0) & (voxels < shape), axis=1)

    labels = np.zeros(len(voxels), dtype=int)
    if in_bounds.any():
        labels[in_bounds] = data[voxels[in_bounds, 0], voxels[in_bounds, 1], voxels[in_bounds, 2]].astype(int)

    max_label = int(labels.max()) if labels.size else 0
    palette = get_palette(max_label + 1)
    colors = [(0.0, 0.0, 0.0) if label == 0
        else tuple(colors_from_csv[label - 1]) if colors_from_csv
        else tuple(palette[label % len(palette)])
        for label in labels]
    return _make_actor(bundle, colors, line_width, opacity)


def tract_single_color(bundle, color, line_width=1, opacity=1.0):
    """Render all streamlines in a single uniform color.

    Parameters
    ----------
    bundle : streamline container
        Streamlines to render.
    color : tuple of float
        RGB color (0–1).
    line_width : int
        Line width.
    opacity : float
        Actor opacity in [0, 1].

    Returns
    -------
    vtkActor
    """
    lines = _normalize_bundle(bundle)
    if not lines:
        raise ValueError("tract_single_color: no valid streamlines found.")
    stream_actor = actor.line(lines, colors=color, lod=False, fake_tube=True, linewidth=line_width)
    stream_actor.GetProperty().SetOpacity(opacity)
    return stream_actor


def tract_direction_color(bundle, line_width=1, opacity=1.0):
    """Color each streamline point by its local orientation (RGB ↔ XYZ)."""
    lines = _normalize_bundle(bundle)
    if not lines:
        raise ValueError("tract_direction_color: no valid streamlines to render.")

    diffs = [np.diff(sl, axis=0) for sl in lines]
    diffs = [np.vstack([d[:1], d]) for d in diffs]
    orientations = np.concatenate(diffs, axis=0).astype(np.float32)

    norms = np.linalg.norm(orientations, axis=1)
    zero_mask = norms < 1e-8
    if zero_mask.any():
        orientations[zero_mask] = (1.0, 0.0, 0.0)

    stream_actor = actor.line(
        lines, colors=colormap.orient2rgb(orientations),
        lod=False, fake_tube=True, linewidth=line_width,
    )
    stream_actor.GetProperty().SetOpacity(opacity)
    return stream_actor

def get_centroid(bundle, n_points=100, thresh=100):
    '''Get bundle centroid(s) from a bundle with a given distance threshold'''
    if isinstance(bundle, np.ndarray):
        bundle = ArraySequence(bundle[:,:,:3])

    ref_bundle = set_number_of_points(bundle, nb_points=n_points)
    metric = AveragePointwiseEuclideanMetric()
    qb = QuickBundles(threshold=thresh, metric=metric)
    clusters = qb.cluster(ref_bundle)
    centroids = Streamlines(clusters.centroids)
    lens = np.asarray(list(length(centroids)))
    return centroids[np.argmax(lens)]

def get_n_segment_by_length(atlas_bundle, s_len=5):
    '''Calculate the number of segments given segment length (mm)'''
    avg_length = np.mean(list(length(atlas_bundle)))
    return max(int(np.round(avg_length / s_len)), 1)

## copied compute_robust_centroid and adapted from parameterization.py:
## https://github.com/wendyfyx/SPECTRA/blob/main/src/spectra/tractometry/parameterization.py
def compute_robust_centroid(
    bundle,
    s_len: float = 5.0,
    ns: int = None,
    thresh: float = 100.0,
    extrapolate_prop: float = 0.3,
    method: str = 'linear',
) -> np.ndarray:
    """
    Compute a robust centroid that extends to the full bundle extent.
    This addresses the problem where the QuickBundles centroid is shorter
    than the longer streamlines, causing very large end segments.

    Parameters
    ----------
    bundle : ArraySequence
        Atlas bundle
    s_len : float, optional
        Target along-tract segment size (mm). Used to compute ns from
        the extended arc length. Mutually exclusive with ns.
    ns : int, optional
        Target number of along-tract segments. Mutually exclusive with s_len.
        When specified, s_len is derived from the extended arc length.
    thresh : float
        QuickBundles distance threshold
    extrapolate_prop : float
        The proportion of the QB centroid arc length to extrapolate by
        on each end. Default: 0.3.
    method : str
        Extrapolation method. Either 'spline' or 'linear' (default).
        'linear' extrapolates from the terminal tangent vectors of the QB
        centroid, more robust when there's branching at the end
        'spline' fits a cubic spline through the QB centroid and evaluates
        it beyond [0, 1]

    Returns
    -------
    robust_centroid : np.ndarray, shape (ns, 3)
        Extended centroid coordinates, evenly spaced in arc-length,
        compatible with get_centroid output.
    """
    if s_len is None and ns is None:
        raise ValueError("At least one of s_len or ns must be provided")
    if method not in ('spline', 'linear'):
        raise ValueError(f"method must be 'spline' or 'linear', got '{method}'")

    # initialize with QuickBundles centroid
    initial_centroid = get_centroid(bundle, n_points=100, thresh=thresh)
    initial_centroid = np.array(initial_centroid)

    # fallback: QB centroid resampled to the correct ns
    def _fallback():
        if ns is not None:
            return np.array(get_centroid(bundle, n_points=ns, thresh=thresh))
        ns_fallback = get_n_segment_by_length(bundle, s_len=s_len)
        return np.array(get_centroid(bundle, n_points=ns_fallback, thresh=thresh))

    # approximate arc length from QB centroid points
    centroid_arc_length = float(
        np.linalg.norm(np.diff(initial_centroid, axis=0), axis=1).sum()
    )
    ext_mm = extrapolate_prop * centroid_arc_length

    if method == 'spline':
        if len(initial_centroid) < 4:
            log.warning(
                "Initial centroid has fewer than 4 points, "
                "cannot fit cubic spline. Falling back."
            )
            return _fallback()

        # fit parametric spline through centroid
        tck, u = splprep(initial_centroid.T, s=0, k=3)

        # convert ext_mm to t-units via terminal derivatives (ds/dt at boundaries)
        deriv_start = np.linalg.norm(np.array(splev(0.0, tck, der=1)))
        deriv_end   = np.linalg.norm(np.array(splev(1.0, tck, der=1)))
        t_ext_start = ext_mm / deriv_start if deriv_start > 0 else 0.1
        t_ext_end   = ext_mm / deriv_end   if deriv_end   > 0 else 0.1

        # single dense sampling over extended t range
        # splev extrapolates linearly outside [0, 1] following terminal curvature
        t_dense = np.linspace(0.0 - t_ext_start, 1.0 + t_ext_end, 1000)
        ext_pts = np.array(splev(t_dense, tck)).T   # (1000, 3)

    else:  # linear
        # extrapolate from terminal tangent vectors of the QB centroid
        tangent_start = initial_centroid[0] - initial_centroid[1]
        tangent_end   = initial_centroid[-1] - initial_centroid[-2]
        tangent_start /= np.linalg.norm(tangent_start)
        tangent_end   /= np.linalg.norm(tangent_end)

        # build n_ext extension points on each side, spaced ~s_len apart
        # use a temporary spacing of 1mm when ns-mode is active (refined later)
        _step = s_len if s_len is not None else 1.0
        n_ext = max(1, int(np.round(ext_mm / _step)))
        steps = np.arange(1, n_ext + 1)[:, np.newaxis]  # (n_ext, 1)
        ext_start_pts = initial_centroid[0] + steps * tangent_start * _step  # (n_ext, 3)
        ext_end_pts   = initial_centroid[-1] + steps * tangent_end   * _step  # (n_ext, 3)

        # prepend/append to centroid (start points in reverse so curve is continuous)
        ext_pts = np.vstack([ext_start_pts[::-1], initial_centroid, ext_end_pts])
        t_dense = None   # not used in linear path

    # build cKDTree on extended curve for endpoint projection
    ext_tree = cKDTree(ext_pts)

    # project streamline endpoints onto the extended curve
    i_starts, i_ends = [], []
    for sl in bundle:
        sl = np.array(sl)
        if len(sl) < 2:
            continue
        _, i_s = ext_tree.query(sl[0])
        _, i_e = ext_tree.query(sl[-1])
        i_starts.append(i_s)
        i_ends.append(i_e)

    if not i_starts:
        log.warning(
            "No valid streamline endpoints found. Falling back."
        )
        return _fallback()

    i_starts = np.array(i_starts)
    i_ends   = np.array(i_ends)

    # handle reversed streamlines
    i_min_per_sl = np.minimum(i_starts, i_ends)
    i_max_per_sl = np.maximum(i_starts, i_ends)

    # robust extent via percentiles
    i_start = int(np.round(np.percentile(i_min_per_sl, 2.0)))
    i_end   = int(np.round(np.percentile(i_max_per_sl, 98.0)))

    if i_end <= i_start:
        log.warning(
            f"i_start ({i_start}) >= i_end ({i_end}). Falling back."
        )
        return _fallback()

    # compute arc length between i_start and i_end
    ext_pts_range = ext_pts[i_start:i_end + 1]

    if len(ext_pts_range) < 2:
        log.warning(
            "Too few samples in range. Falling back."
        )
        return _fallback()

    segment_lengths = np.linalg.norm(np.diff(ext_pts_range, axis=0), axis=1)
    arc_length = float(segment_lengths.sum())

    # Derive ns (and s_len) for resampling
    if ns is not None:
        ns_resample = max(ns, 1)
        s_len_derived = arc_length / ns_resample
    else:
        ns_resample = max(int(np.round(arc_length / s_len)), 1)
        s_len_derived = s_len

    cum_lengths = np.concatenate([[0.0], np.cumsum(segment_lengths)])
    target_lengths = np.linspace(0.0, arc_length, ns_resample)

    if method == 'spline':
        # interpolate back to t values then evaluate spline for smooth output
        t_range = t_dense[i_start:i_end + 1]
        t_resampled = np.interp(target_lengths, cum_lengths, t_range)
        robust_centroid = np.array(splev(t_resampled, tck)).T
    else:
        # interpolate directly on the extended point array
        robust_centroid = np.array([
            np.interp(target_lengths, cum_lengths, ext_pts_range[:, dim])
            for dim in range(3)
        ]).T

    log.info(
        f"({method}): extended centroid to {ns_resample} points "
        f"(arc_length={arc_length:.1f}mm, s_len={s_len_derived:.2f}mm)"
    )
    return robust_centroid


## added support... 
def tract_segmented_color(bundle, method, num_segments, s_len=None, line_width=1, opacity=1.0,
                colors_from_csv=None, bundle_shape=None, affine=None):
    """Segment and color a bundle using centerline or hyperplane parcellation.

    Parameters
    ----------
    bundle : streamline container
        Streamlines to render.
    method : {'centerline', 'hyperplane', 'linear', 'spline'}
        Segmentation strategy.
    num_segments : int
        Number of segments when no CSV colors are provided. Required for
        'centerline' and 'hyperplane'. Optional for the projection methods when ``s_len`` is supplied.
    s_len : float, optional
        Target along-tract segment length in mm. Used by 'linear' and
        'spline' only; ignored when ``num_segments`` is given.
    line_width : int
        Line width.
    opacity : float
        Actor opacity in [0, 1].
    colors_from_csv : list of RGB tuples, optional
        Per-segment colors from a statistics CSV. Auto-generated if None.
    bundle_shape : tuple of int
        Voxel dimensions of the reference volume (required for 'hyperplane').
    affine : ndarray of shape (4, 4)
        Reference affine (required for 'hyperplane').

    Returns
    -------
    vtkActor
    """

    if method in ('centerline', 'hyperplane'):
        if num_segments is None:
            raise ValueError(f"--num_segments is required for --seg_method {method}.")
        if s_len is not None:
            log.warning("--s_len is ignored when --seg_method is %r.", method)
    elif method in ('linear', 'spline'):
        if num_segments is None and s_len is None:
            log.info("Neither --num_segments nor --s_len given; " "falling back to default s_len=5.0 mm.")
            s_len = 5.0
        elif num_segments is not None and s_len is not None:
            log.info("Both --num_segments and --s_len given; --num_segments will be used.")
            s_len = None
    else:
        raise ValueError(
            f"Unknown segmentation method: {method!r}. Expected one of: "
            "centerline, hyperplane, linear, spline."
        )

    has_colors = bool(colors_from_csv)
    if has_colors and len(colors_from_csv) > 1:
        num_segments = len(colors_from_csv)

    if num_segments is not None:
        palette = get_palette(num_segments + 1)
        colors = colors_from_csv if has_colors else [palette[i % len(palette)] for i in range(1, num_segments + 1)]
    else:
        palette = None
        colors = None

    if method in ('centerline', 'hyperplane'):

        corres_points, original_indices = get_alignment(model_sls = bundle, subj_sls = bundle, num_segments = num_segments, affine=affine, method = method)
        bundle_img = bundle_density(bundle, bundle_shape, affine)
        mask_data = bundle_img.get_fdata()

        segments = segment_bundle(bundle_data = mask_data, corres_pts = corres_points, num_segments = len(original_indices))
        segmented_bundle = np.zeros(mask_data.shape)
        for new_i, orig_i in enumerate(original_indices):
            segmented_bundle[segments[new_i]] = orig_i + 1

        pts = np.vstack(list(bundle))
        inv_affine = np.linalg.inv(affine)
        voxels = np.round(nib.affines.apply_affine(inv_affine, pts)).astype(int)
        shape = np.asarray(segmented_bundle.shape)
        in_bounds = np.all((voxels >= 0) & (voxels < shape), axis=1)

        labels = np.zeros(len(voxels), dtype=int)
        if in_bounds.any():
            labels[in_bounds] = segmented_bundle[voxels[in_bounds, 0], voxels[in_bounds, 1], voxels[in_bounds, 2]].astype(int)
        segments_colors = [(0.0, 0.0, 0.0) if label == 0 else tuple(colors[label - 1]) for label in labels]

        return _make_actor(bundle, segments_colors, line_width, opacity)
    
    if method in ('linear', 'spline'):
        extrap = method
        centroid_data = compute_robust_centroid(
            bundle,
            ns=num_segments,
            s_len=s_len if s_len is not None else 5.0,
            thresh=100.0,
            method=extrap,
        )

        if colors is None:
            num_segments = len(centroid_data)
            palette = get_palette(num_segments + 1)
            colors = [palette[i % len(palette)] for i in range(1, num_segments + 1)]

        points = np.vstack(list(bundle))
        _, indx = cKDTree(centroid_data, copy_data=True).query(points, k=1)
        segments_colors = [tuple(colors[i]) for i in indx]
        return _make_actor(bundle, segments_colors, line_width, opacity)
