import numpy as np
from collections import defaultdict
from tslearn.metrics import dtw_path

from meta.core.corresponds import get_centroids, min_distance_filter
from meta.utils.tractogram import reorient_streamlines

from dipy.tracking.streamline import length, transform_streamlines


def get_alignment(model_sls, subj_sls, num_segments, affine, method="hyperplane", min_spacing=0.5):
    """
    Get the alignment between model and subject streamlines.

    Parameters
    ----------
    model_sls: List of model streamlines.
    subj_sls: List of subject streamlines.
    num_segments: Number of segments for alignment.
    affine: Affine transformation matrix.
    method: Correspondence method. One of 'hyperplane' or 'centerline'.
    min_spacing: Minimum allowed distance (in voxels) between consecutive correspondence
        points; passed to min_distance_filter to drop DTW-collapsed points.

    Returns
    -------
    out_pts: List of updated correspondences using DTW.
    original_indices: Indices of DTW points.
    """

    if method not in ("hyperplane", "centerline"):
        raise ValueError("method must be either 'hyperplane' or 'centerline'.")

    ## Transform model to subject space:
    model_sls = transform_streamlines(model_sls, np.linalg.inv(affine))

    ## Subject bundle:
    subj_sls = transform_streamlines(subj_sls, np.linalg.inv(affine))

    if method == "hyperplane":
        model_ctr = get_centroids(model_sls, n_points=num_segments, threshold=2.0, sort_by="cluster_size", n_centroids=1)
        subj_ctr = get_centroids(subj_sls, n_points=500, threshold=10.0, sort_by="cluster_size", n_centroids=1)
        subj_ctrs = get_centroids(subj_sls, n_points=500, threshold=0.01, num_clusters=500)
    else:
        model_ctr = get_centroids(model_sls, n_points=num_segments, threshold=2.0, sort_by="length", n_centroids=1)
        subj_ctr = get_centroids(subj_sls, n_points=500, threshold=6.0, sort_by="length", n_centroids=1)
        subj_ctrs = get_centroids(subj_sls, n_points=500, threshold=6.0, num_clusters=500, sort_by="length", n_centroids=1)

    ## Check if the subject centroids are flipped compared to the model:
    subj_ctr = reorient_streamlines(subj_ctr, model_ctr)
    subj_ctrs = reorient_streamlines(subj_ctrs, model_ctr)

    ## Compute the correspondence between model and subject centroids:
    dtw_pts = []
    for model_sl, subj_sl in zip(model_ctr, subj_ctr):
        dtw_pairs, similarity_score = dtw_path(model_sl, subj_sl)

        model_to_subj = defaultdict(list)
        for mi, si in dtw_pairs:
            model_to_subj[mi].append(si)

        kept_pairs = set()
        multi_idx = {mi for mi, si in model_to_subj.items() if len(si) > 1}

        if multi_idx:
            first_real = min(multi_idx)
            last_real = max(multi_idx)
            for mi in range(first_real, last_real + 1):
                si = model_to_subj[mi]
                kept_pairs.add((mi, si[len(si) // 2]))
            for mi, si in model_to_subj.items():
                if mi < first_real or mi > last_real:
                    kept_pairs.add((mi, si[len(si) // 2]))
        else:
            for mi, si in model_to_subj.items():
                kept_pairs.add((mi, si[len(si) // 2]))

        ref_full = np.full((num_segments, 3), np.nan, dtype=float)
        for mi, si in kept_pairs:
            ref_full[mi] = subj_sl[si]
        dtw_pts.append(ref_full)

    ref_full = dtw_pts[0]
    valid_idx = np.where(~np.isnan(ref_full).all(axis=1))[0]
    n_valid = len(valid_idx)

    if n_valid == 0:
        raise ValueError("DTW correspondence did not keep any model positions.")

    ref_pts = ref_full[valid_idx]

    def expand_to_model(corr_pts, orig_idx, n_model):
        full = np.full((n_model, 3), np.nan, dtype=float)
        for k, idx in enumerate(orig_idx):
            if k < len(corr_pts):
                full[idx] = corr_pts[k]

        for dim in range(3):
            known = ~np.isnan(full[:, dim])
            kx = np.where(known)[0]
            ky = full[known, dim]
            if len(kx) >= 2:
                full[:, dim] = np.interp(np.arange(n_model), kx, ky)
            elif len(kx) == 1:
                full[:, dim] = ky[0]
        return full

    subj_pts = []
    for subj_sl in subj_ctrs:
        subj_sl = np.squeeze(subj_sl)
        dtw_pairs, similarity_score = dtw_path(ref_pts, subj_sl)
        ref_to_ctr = defaultdict(list)
        for ref_i, ctr_i in dtw_pairs:
            ref_to_ctr[ref_i].append(ctr_i)

        ctr_pts = []
        for ref_i in range(n_valid):
            ctr_idx = ref_to_ctr[ref_i]
            ctr_pts.append(subj_sl[ctr_idx[len(ctr_idx) // 2]])

        full_ctr = expand_to_model(ctr_pts, valid_idx, num_segments)
        subj_pts.append(full_ctr)

    ref_expanded = expand_to_model(ref_pts, valid_idx, num_segments)
    all_pts = np.stack([ref_expanded] + subj_pts, axis=0)

    lengths = [length(sl) for sl in all_pts]
    mean_length = np.mean(lengths)
    std_length = np.std(lengths)
    length_threshold = mean_length - (3 * std_length)

    short_idx = np.where(np.array(lengths) < length_threshold)[0]
    filt_pts = [sl for idx, sl in enumerate(all_pts) if idx not in short_idx]

    ## Compute pairwise distances:
    corr_pts = np.array(filt_pts)
    pair_dists = np.zeros((corr_pts.shape[1], corr_pts.shape[0], corr_pts.shape[0]))
    for i in range(corr_pts.shape[1]):
        for j in range(corr_pts.shape[0]):
            for k in range(j + 1, corr_pts.shape[0]):
                pair_dists[i, j, k] = np.linalg.norm(corr_pts[j, i] - corr_pts[k, i])

    n_streamlines = corr_pts.shape[0]
    lower_tri_mask = np.tril(np.ones((n_streamlines, n_streamlines), dtype=bool))
    pair_dists[:, lower_tri_mask] = np.nan

    std_dists = np.nanstd(pair_dists, axis=(1, 2))
    core_idx = np.where(std_dists <= 5)[0]

    if core_idx.size == 0 and not np.all(np.isnan(std_dists)):
        median_std = np.nanmedian(std_dists)
        core_idx = np.where(std_dists <= median_std)[0]

    if core_idx.size > 0:
        core_start = core_idx[0]
        core_end = core_idx[-1]
        out_pts = []

        for array in filt_pts:
            merged = []
            if core_start > 1:
                start_pt = array[0]
                end_pt = array[core_start]
                side_1_pts = np.linspace(start_pt, end_pt, core_start + 1)[1:-1]
                merged.extend(array[0:1])
                merged.extend(side_1_pts)
            else:
                merged.extend(array[0:core_start])

            merged.extend(array[core_start:core_end + 1])
            if num_segments - core_end > 1:
                start_pt = array[core_end]
                end_pt = array[-1]
                side_2_pts = np.linspace(start_pt, end_pt, num_segments - core_end)[1:-1]
                merged.extend(side_2_pts)
                merged.extend(array[-1:])

            out_pts.append(np.array(merged))
    else:
        out_pts = filt_pts

    return min_distance_filter(out_pts, min_spacing=min_spacing, detect_pts=filt_pts)
