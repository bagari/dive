import os
import sys
import logging
import argparse
import nibabel as nib
from importlib.resources import files

from dive import __version__
from dive.ui.core import Show
from dive.utils.color import parse_color
from dive.core.scene import load_scene_objects
from dive.core.brain_2d import brain_actor, glass_actor

log = logging.getLogger(__name__)
def _configure_logging(verbose: bool):
    logging.basicConfig(
        stream=sys.stdout,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.WARNING,
    )
    logging.getLogger("dive").setLevel(logging.DEBUG if verbose else logging.INFO)
    if not verbose:
        logging.getLogger("nibabel.global").setLevel(logging.ERROR)
        try:
            from vtkmodules.vtkCommonCore import vtkLogger
            vtkLogger.SetStderrVerbosity(vtkLogger.VERBOSITY_ERROR)
        except Exception:
            pass

### Constants ###
_ASSETS = files("dive").joinpath("assets")
_DEFAULT_BRAIN_2D = str(_ASSETS.joinpath("MNI_ICBM152_brain.nii.gz"))
_DEFAULT_GLASS_BRAIN = str(_ASSETS.joinpath("MNI_ICBM152_WM.nii.gz"))
_ALL_VIEWS = ("Axial_S", "Axial_I", "Coronal_A", "Coronal_P", "Sagittal_L", "Sagittal_R")


def main():
    print("dive-mri (DiVE) | Iyad Ba Gari | https://github.com/bagari/dive", file=sys.stderr)
    parser = argparse.ArgumentParser(
        prog="dive",
        description="DiVE — Diffusion Visualization and Explorer. "
                    "Author: Iyad Ba Gari <iyad.bagari@usc.edu>. "
                    "Repository: https://github.com/bagari/dive")
    parser.add_argument("--version", action="version", version=f"dive {__version__}")
    
    # Tract arguments
    parser.add_argument("--tract", nargs="*", default=[],
                        help="One or more tractogram files (TRK/TCK/TRX/.tt.gz)")
    parser.add_argument("--tract_colors", nargs="+", type=parse_color, default=[],
                        help="Colors for tracts, e.g. red blue '#00ff00'")
    parser.add_argument("--tract_opacity", nargs="+", type=float, default=[],
                        help="Opacity values for tracts, e.g. 0.5 0.8 1.0")
    parser.add_argument("--tract_width", type=int, default=1,
                        help="Streamline tube width in pixels")

    # Mask / ROI arguments
    parser.add_argument("--mask", nargs="*", default=[],
                        help="One or more NIfTI label files")
    parser.add_argument("--mask_colors", nargs="+", type=parse_color, default=[],
                        help="Colors for masks, e.g. '#00ff00' red orange")
    parser.add_argument("--mask_opacity", nargs="+", type=float, default=[],
                        help="Opacity values for masks")

    # Mesh arguments
    parser.add_argument("--mesh", nargs="*", default=[],
                        help="One or more VTK mesh files")
    parser.add_argument("--mesh_colors", nargs="+", type=parse_color, default=[],
                        help="Colors for meshes")
    parser.add_argument("--mesh_opacity", nargs="+", type=float, default=[],
                        help="Opacity values for meshes")

    # Interface
    parser.add_argument("--mode", choices=("interactive", "cli", "movie"), default="interactive",
                        help="GUI ('interactive'), batch screenshots ('cli') or movie recording ('movie')")
    parser.add_argument("--background", type=int, choices=(0, 1), default=0,
                        help="Background color: 0 = black, 1 = white")
    parser.add_argument("--zoom", type=float, default=1.0,
                        help="Zoom factor for the standard view")

    # Brain templates (MNI): ToDo maybe add threshold to control visibility Iyad
    parser.add_argument("--brain_2d", nargs="?",
                        const=_DEFAULT_BRAIN_2D, default=None, metavar="PATH",
                        help="NIfTI for the 2D slice. Omit PATH to use the bundled MNI T1.")
    parser.add_argument("--glass_brain", nargs="?",
                        const=_DEFAULT_GLASS_BRAIN, default=None, metavar="PATH",
                        help="NIfTI binary for 3D glass-brain. Omit PATH for the bundled MNI WM.")

    # Statistics
    parser.add_argument("--output", default=None,
                        help="Output path stem for screenshots (cli mode)")
    parser.add_argument("--map", default="RdBu",
                        help="Matplotlib colormap name")
    parser.add_argument("--value_range", nargs=2, type=float, default=None,
                        help="MIN MAX clamp for value-mapped colormaps")
    parser.add_argument("--stats_csv", nargs="+", default=[],
                        help="One or more statistics CSVs (segment, value, p_value)")
    parser.add_argument("--group_stat",default=None,
                        help="Group name to filter statistics CSVs")
    parser.add_argument("--threshold", type=float, default=0.05,
                        help="P-value cutoff above which rows are gray")
    parser.add_argument("--log_p_value", action="store_true",
                        help="Use -log10(p_value) instead of value")

    # Segmentation
    parser.add_argument("--num_segments", type=int, default=None,
                        help="Number of segments along each tract")
    parser.add_argument("--s_len", type=float, default=None, help="Target along-tract segment length in mm. "
                        "Used by 'linear' and 'spline' only. "
                        "Ignored if --num_segments is also given.")
    parser.add_argument("--seg_method", choices=("centerline", "hyperplane", "linear", "spline"),
                        default=None, help="Segmentation methods")

    # Linear / non-linear transforms
    parser.add_argument("--transform", default=None,
                        help="Affine matrix: MNI → subject space")
    parser.add_argument("--inverse", action="store_true",
                        help="Invert the supplied affine (subject → MNI)")
    parser.add_argument("--warp", default=None,
                        help="Non-linear warp field")
    parser.add_argument("--warp_ref", default=None,
                        help="Reference image for the warp (required if --warp is given)")
    parser.add_argument("--warp_source", choices=("ants", "dsi_studio"), default="dsi_studio",
                        help="Warp convention method")
    parser.add_argument("--warp_first", action="store_true",
                        help="Apply the warp before the affine transform")
    parser.add_argument("--no_trim", action="store_true",
                        help="Keep endpoints outside the warp grid")

    # Camera
    parser.add_argument("--cam_view", nargs="+", choices=_ALL_VIEWS,
                        default=None, metavar="VIEW",
                        help="One or more camera views; defaults to all six")

    # Movie recording
    parser.add_argument("--movie_axis", choices=("yaw", "pitch"), default="yaw")
    parser.add_argument("--movie_duration", type=float, default=8.0)
    parser.add_argument("--movie_fps", type=int, default=30)
    parser.add_argument("--movie_size", default="1920x1080", help="WIDTHxHEIGHT, e.g. 1920x1080")
    parser.add_argument("--movie_loops", type=int, default=1)
    parser.add_argument("--movie_elevation", type=float, default=0.0)
    parser.add_argument("--movie_show_slice", action="store_true")

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")


    if len(sys.argv) == 1:
        parser.print_help()
        return
    args = parser.parse_args()
    _configure_logging(args.verbose)

    camera_views = args.cam_view or _ALL_VIEWS

    viewer  = Show(background = args.background, zoom = args.zoom)
    scene = viewer.build_scene()

    rois = load_scene_objects(
        masks = args.mask,
        tracts = args.tract,
        meshes = args.mesh,
        mask_colors = args.mask_colors,
        tract_colors = args.tract_colors,
        mesh_colors = args.mesh_colors,
        mask_opacity = args.mask_opacity,
        tract_opacity = args.tract_opacity,
        mesh_opacity = args.mesh_opacity,
        stats_csv = args.stats_csv,
        group_stat = args.group_stat,
        colormap = args.map,
        value_range = args.value_range,
        threshold = args.threshold,
        log_p_value = args.log_p_value,
        tract_width = args.tract_width,
        segmentation_method = args.seg_method,
        num_segments = args.num_segments,
        s_len = args.s_len,
        transform = args.transform,
        inverse = args.inverse,
        warp = args.warp,
        warp_ref = args.warp_ref,
        warp_source = args.warp_source,
        warp_first = args.warp_first,
        trim_endpoints = not args.no_trim,
        output = args.output,
    )

    for roi_actor in rois.values():
        scene.add(roi_actor)

    ## GUI display: rois names:
    mask_basenames = {os.path.basename(p) for p in args.mask}
    mesh_basenames = {os.path.basename(p) for p in args.mesh}
    display_groups = {'Tract': [], 'Mask': [], 'Mesh': [], 'Brain': []}
    for name in rois:
        if name in mask_basenames:
            display_groups['Mask'].append(name)
        elif name in mesh_basenames:
            display_groups['Mesh'].append(name)
        else:
            display_groups['Tract'].append(name)

    ## GUI comboboxes:
    if not display_groups['Tract']:
        display_groups['Tract'] = ['<no tract loaded>']
    if not display_groups['Mask']:
        display_groups['Mask']  = ['<no mask loaded>']
    if not display_groups['Mesh']:
        display_groups['Mesh']  = ['<no mesh loaded>']

    ## Brain images
    if args.brain_2d:
        display_groups['Brain'] = [os.path.basename(args.brain_2d)]
    else:
        display_groups['Brain'] = ['<no 2D brain loaded>']

    ## Load Glass brain (WM):
    if args.glass_brain:
        glass = glass_actor(args.glass_brain)
        scene.add(glass)
        rois[display_groups['Brain'][0]] = glass

    ## Load 2D brain slice:
    if args.brain_2d:
        brain_img = nib.load(args.brain_2d)
        slice_actor = brain_actor(brain_img)
        slice_idx = min(brain_img.get_fdata().shape)
        viewer.set_max_view(slice_idx, slice_actor=slice_actor)
        scene.add(slice_actor)
        rois[display_groups['Brain'][0]] = slice_actor
        
    log.info("Initialized scene with %d ROIs: %s", len(rois), list(rois.keys()))
    viewer.init_show_manager(
        display_groups=display_groups,
        rois=rois,
        mode=args.mode,
        camera_view=camera_views,
        output_path=args.output,
        movie_axis=args.movie_axis,
        movie_duration=args.movie_duration,
        movie_fps=args.movie_fps,
        movie_size=args.movie_size,
        movie_loops=args.movie_loops,
        movie_elevation=args.movie_elevation,
        movie_show_slice=args.movie_show_slice,
    )
