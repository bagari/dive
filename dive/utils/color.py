import os
import argparse
import webcolors
import distinctipy
import numpy as np
import collections
import pandas as pd
from math import isnan
import matplotlib
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from functools import lru_cache


@lru_cache(maxsize=None)
def _default_palette():
    """50 distinct QC colors, computed lazily on first use."""
    return distinctipy.get_colors(50, rng=0)


def get_palette(n):
    """Return at least *n* distinct colors.
    """
    cache = _default_palette()
    if n <= len(cache):
        return cache
    return distinctipy.get_colors(n, rng=0)


def get_color(color_idx):
    """Return one RGB color from the cached palette by index.
    """
    cache = _default_palette()
    return cache[color_idx % len(cache)]


def parse_color(color):
    color = color.strip()
    if color.startswith("#"):
        h = color[1:]
        if len(h) == 3:
            h = "".join(c*2 for c in h)
        if len(h) != 6:
            raise argparse.ArgumentTypeError(f"Invalid hex color: {color}")
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        return (r/255.0, g/255.0, b/255.0)
    try:
        r, g, b = webcolors.name_to_rgb(color.lower())
        return (r/255.0, g/255.0, b/255.0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Unknown color name: {color}")


def assign_colors(stats_csv, cmap_name, range_value=None, log_p_value=False, threshold=None,
                output=None, filename="_color_bar.pdf", group_stat=None):
    """
    Map CSV values to RGB colors via a matplotlib colormap.

    Parameters
    ----------
    stats_csv   : Path to CSV with columns 'segment', 'value', 'p_value'
                (and optionally 'groups' for group filtering).
    cmap_name   : Matplotlib colormap name (e.g. 'RdBu').
    range_value : [min, max] to clamp normalization; uses data range if empty.
    log_p_value : If True, colour by -log10(p_value) instead of 'value'.
    threshold   : p_value cutoff; rows above it are painted gray.
                Only active when range_value is provided.
    output      : Directory to save the colorbar image; skipped if None.
    filename    : Colorbar image filename.
    group_stat  : If set, filter to rows where 'groups' == group_stat first.

    Returns
    -------
    np.ndarray of shape (N, 3) with RGB values in [0, 1].
    """
    df = pd.read_csv(stats_csv)

    if group_stat is not None:
        df = df[df["groups"] == group_stat].copy()

    range_value = list(range_value) if range_value else []
    use_range = bool(range_value)
    col = "p_value" if log_p_value else "value"

    if log_p_value:
        df[col] = -np.log10(df[col])

    if use_range:
        df.sort_values(by="segment", inplace=True)

    vmin = range_value[0] if use_range else df[col].min()
    vmax = range_value[1] if use_range else df[col].max()

    cmap = matplotlib.colormaps[cmap_name]
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    df["_norm"] = norm(df[col]).clip(0, 1)

    def to_rgb(norm_val: float, p_val: float):
        if use_range and threshold is not None and p_val > threshold:
            return [0.5, 0.5, 0.5]
        r, g, b, _ = cmap(norm_val)
        return [r, g, b]

    color_map = collections.OrderedDict(
        sorted(
            {
                label: to_rgb(n, p)
                for n, p, label in zip(df["_norm"], df["p_value"], df["segment"])
                if not isnan(label)
            }.items()
        )
    )

    if output is not None:
        fig, ax = plt.subplots(figsize=(6, 1))
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        fig.colorbar(sm, cax=ax, orientation="horizontal")
        plt.savefig(os.path.join(output, filename.lstrip("_")), bbox_inches="tight", dpi=300)
        plt.close(fig)

    return list(color_map.values())  
