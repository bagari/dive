[![PyPI](https://img.shields.io/pypi/v/dive-mri?label=PyPI)](https://pypi.org/project/dive-mri/)
[![FURY](https://img.shields.io/badge/Built%20with-FURY-red)](https://fury.gl/latest/index.html)
[![VTK / OpenGL](https://img.shields.io/badge/Rendering-VTK%20%2F%20OpenGL-5586A4)](https://www.opengl.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE.txt)

<br />
<div align="center">
  <a href="https://raw.githubusercontent.com/bagari/dive/main/resources/Logo.svg">
    <img src="https://raw.githubusercontent.com/bagari/dive/main/resources/Logo.svg" alt="Logo" width="80" height="80">
  </a>

<h3 align="center">DiVE</h3>

  <p align="center">
    Diffusion Visualization and Explorer
    <br />
    <a href="#usage"><strong>Explore usage »</strong></a>
    <br />
    <br />
    <a href="https://github.com/bagari/dive/issues">Report Bug</a>
    ·
    <a href="https://github.com/bagari/dive/issues">Request Feature</a>
  </p>
</div>



## About The Project

Diffusion Visualization and Explorer (DiVE) is a command-line tool for visualizing diffusion MRI and medical imaging data. It supports tractography (TRK, TCK, TRX, TinyTrack), NIfTI masks, and VTK meshes, which can be displayed individually or overlaid with anatomical slices and a 3D glass brain. DiVE provides streamline coloring by orientation, labels, or along-tract statistics, supports linear and non-linear spatial transformations (ANTs/DSI Studio), and enables interactive visualization as well as high quality image and video export for presentations and publications.

<div align="center">
  <img src="https://raw.githubusercontent.com/bagari/dive/main/resources/dive_overview.png" alt="DiVE overview — interactive 3D scene alongside the control panel" width="100%">
</div>

## Demo

A 360° rotation exported with DiVE's `movie` mode:

<video src="https://github.com/bagari/dive/raw/main/resources/dive_movie.mp4" controls muted loop width="100%">
  Your browser can't play this video inline —
  <a href="https://github.com/bagari/dive/raw/main/resources/dive_movie.mp4">download / watch the demo (MP4)</a>.
</video>

If the player above doesn't appear, watch it here: [**▶ dive_movie.mp4**](https://github.com/bagari/dive/raw/main/resources/dive_movie.mp4)

## Getting Started

### Requirements

| | |
|---|---|
| **Python** | 3.11, 3.12, or 3.13 |
| **OS** | macOS, Linux, and Windows (offscreen rendering supported) |
| **GPU** | Not required - DiVE renders via VTK / OpenGL on the host |
| **Movies** | H.264 encoding is bundled via PyAV — **no system `ffmpeg` needed** |

### Installation

Using **pip**:
```sh
pip install dive-mri
```

Using **Bioconda**:
```sh
conda config --add channels bioconda
conda install bioconda::dive-mri
```

<details>
<summary>Quick sanity check</summary>

The bundled MNI templates let you smoke-test without downloading anything:

```sh
# Opens a 3D window with a glass brain + MNI T1 slice
dive --brain_2d --mode interactive

# CLI
dive --glass_brain --mode cli --background 1 --output .
```
</details>

## Modes

DiVE has one entry point (`dive`) and three rendering modes selected via `--mode`. The same data-loading pipeline runs in every mode; only where the frames go changes.

| | `interactive` (default) | `cli` | `movie` |
|---|:---:|:---:|:---:|
| Opens a window | ✅ | ❌ | ❌ |
| Cluster friendly | ❌ (needs a display) | ✅ | ✅ |
| Output | 3D UI | one PNG per view | one MP4 |
| Requires `--output` | no | **yes** | **yes** |
| Camera View | — | ✅ | orbit (not fixed views) |

```sh
dive --mode interactive   # Default, open a 3D window with GUI
dive --mode cli           # Render PNGs to disk and exit
dive --mode movie         # Create movie
```


## Usage

```sh
# Interactive mode: along-tract segments (CST_R) mask colored by CSV statistics, (color map RdBu_r, min/max to ±5, segments with p > 0.05 grayed out and a white-background glass brain)
dive --mask resources/meta_CST_R_15_segments.nii.gz \
     --stats_csv resources/stat_template.csv --map RdBu_r --threshold 0.05 \
     --value_range -5 5 --tract resources/CST_L.trk --tract_width 5 \
     --mode interactive --glass_brain --background 1
```

```sh
# Movie mode: two meshes (IFOF_R in green, AF_L in red) + along-tract segments (CST_L) mask + a CST_R TinyTrack bundle → a 16 s, 1080p rotation written to resources/dive_movie_1.mp4
dive --mesh resources/IFOF_R.vtk resources/AF_L.vtk --mesh_colors green red \
     --mask resources/meta_CST_L_15_segments.nii.gz \
     --tract resources/CST_R.tt.gz --tract_width 5 \
     --glass_brain --mode movie --background 1 \
     --output resources/dive_movie_1.mp4 \
     --movie_duration 16 --movie_fps 30 --movie_size 1920x1080
```

**Transforms — subject ↔ MNI, on the fly (data on disk is never modified):**

```sh
# DSI Studio, subject → MNI (the warp already includes the affine)
dive --tract subject.tt.gz --glass_brain --background 1 \
     --warp 1Warp.nii.gz --warp_source dsi_studio --warp_ref MNI_QA.nii.gz

# ANTs, subject → MNI (inverse affine + inverse warp)
dive --tract subject.tt.gz --glass_brain --background 1 \
     --transform 0GenericAffine.mat --inverse \
     --warp 1InverseWarp.nii.gz --warp_source ants
```

## CLI Options

Run `dive --help` for the full list. Grouped reference below.

<details>
<summary><strong>All flags (grouped)</strong></summary>

**Mode**

| Flag | Default | Description |
|---|---|---|
| `--mode {interactive,cli,movie}` | `interactive` | GUI, batch PNGs, or MP4 recording |
| `-v`, `--verbose` | off | DEBUG-level logging from `dive.*` modules |
| `--version` | — | Print version and exit |

**Tracts**

| Flag | Default | Description |
|---|---|---|
| `--tract FILE...` | `[]` | Tractograms (`.trk` / `.tck` / `.trx` / `.tt.gz`) |
| `--tract_colors COLOR...` | `[]` | Per-tract color: name (`red`), hex (`#00ff00`) |
| `--tract_opacity FLOAT...` | `1` | Per-tract opacity in `[0, 1]` |
| `--tract_width INT` | `1` | Streamline tube width in pixels |

**Masks (ROIs) & meshes**

| Flag | Default | Description |
|---|---|---|
| `--mask FILE...` | `[]` | NIfTI label files (`.nii` / `.nii.gz`) |
| `--mask_colors COLOR...` | `[]` | Per-mask color (single-label masks only) |
| `--mask_opacity FLOAT...` | `1` | Per-mask opacity |
| `--mesh FILE...` | `[]` | VTK PolyData files |
| `--mesh_colors COLOR...` | `[]` | Per-mesh color |
| `--mesh_opacity FLOAT...` | `1` | Per-mesh opacity |

**Anatomical context & display**

| Flag | Default | Description |
|---|---|---|
| `--brain_2d [PATH]` | none | NIfTI rendered as a 2D slice. Omit `PATH` for the bundled MNI T1 |
| `--glass_brain [PATH]` | none | Binary NIfTI rendered as a translucent isosurface. Omit `PATH` for the bundled MNI WM |
| `--background {0,1}` | `0` | `0` = black, `1` = white |
| `--zoom FLOAT` | `1.0` | Multiplicative camera zoom |

**Output & statistics**

| Flag | Default | Description |
|---|---|---|
| `--output STEM` | none | Output path stem. Required for `cli` and `movie` modes |
| `--stats_csv FILE...` | `[]` | Statistics CSVs (`segment,value,p_value`); pair by position with `--tract` |
| `--group_stat NAME` | none | Filter CSV rows where `groups == NAME` |
| `--map NAME` | `RdBu` | Any matplotlib colormap (`viridis`, `plasma`, …) |
| `--value_range MIN MAX` | none | Clamp colormap normalization |
| `--threshold FLOAT` | `0.05` | Rows with `p_value >` this render gray (active with `--value_range`) |
| `--log_p_value` | off | Color by `−log10(p_value)` instead of `value` |

**Segmentation**

| Flag | Default | Description |
|---|---|---|
| `--seg_method {centerline,hyperplane,linear,spline}` | none | Along-tract parcellation method |
| `--num_segments INT` | none | Number of along-tract segments |
| `--s_len FLOAT` | none | Target segment length in mm (`linear` / `spline` only; ignored if `--num_segments` is set) |

**Transforms**

| Flag | Default | Description |
|---|---|---|
| `--transform PATH` | none | Affine matrix (`.txt` / `.npy` / `.mat` / `.mz`) |
| `--inverse` | off | Apply the inverse of the affine |
| `--warp PATH` | none | Non-linear warp field NIfTI |
| `--warp_ref PATH` | none | Reference image for the warp (**required** with `--warp`) |
| `--warp_source {ants,dsi_studio}` | `dsi_studio` | Displacement convention |
| `--warp_first` | off | Apply warp before the affine |
| `--no_trim` | off | Keep streamline endpoints outside the warp grid |

**Camera & movie**

| Flag | Default | Description |
|---|---|---|
| `--cam_view VIEW...` | all six | Subset of `Axial_S` `Axial_I` `Coronal_A` `Coronal_P` `Sagittal_L` `Sagittal_R` (cli mode) |
| `--movie_axis {yaw,pitch}` | `yaw` | Orbit axis |
| `--movie_duration FLOAT` | `8.0` | Seconds |
| `--movie_fps INT` | `30` | Frames per second |
| `--movie_size WxH` | `1920x1080` | e.g. `1280x720`, `3840x2160` |
| `--movie_loops INT` | `1` | Full revolutions |
| `--movie_elevation FLOAT` | `0.0` | Degrees above/below the orbit equator |
| `--movie_show_slice` | off | Keep the 2D slice visible during rotation |

</details>

## UI Interaction

1. <strong>Choose Type:</strong> Use the ROI type (Mask/Mesh/Tract/Brain) to open the drop-down of all files of that type, and select the one you want.
2. <strong>Change View:</strong> Click the buttons to switch to Sagittal / Coronal / Axial view.
3. <strong>Choose Slice:</strong> Change the brain slice value for the selected view (requires a `--brain_2d` file).
4. <strong>Change Opacity (Streamlines, Mask, Mesh, Slice):</strong> Use the sliders to change the opacity of the selected file.
5. <strong>Add Button:</strong> To add more items, click the add (`+`) button and choose the type of file to add.
6. <strong>Remove Button:</strong> To remove a file, select it via Choose Type, then click the remove (`−`) button.

Mouse: left-drag rotates, middle-drag pans, scroll zooms. `R` resets the camera, `S`/`W` toggle surface/wireframe. _The full control panel is shown on the right in the [overview above](#about-the-project)._

## Contributing

Bug reports and feature requests are welcome via the [issue tracker](https://github.com/bagari/dive/issues). For code contributions, fork the repo, create a feature branch, and open a pull request against `main`.

## Acknowledgments

* [Siddharth Narula, Iyad Ba Gari, Shruti P. Gadewar, Sunanda Somu, Neda Jahanshad, "Diffusion Visualization Explorer (DiVE)" Organization for Human Brain Mapping (OHBM 2024) June 26, 2024](https://drive.google.com/file/d/1dsYLTrbfHmrlJNzih-CqbMye32q3sPfU/view)

* [Iyad Ba Gari, Shayan Javid, Alyssa H. Zhu, Shruti P. Gadewar, Siddharth Narula, Abhinaav Ramesh, Sophia I. Thomopoulos et al. "Along-Tract Parameterization of White Matter Microstructure using Medial Tractography Analysis (MeTA)." In 2023 19th International Symposium on Medical Information Processing and Analysis (SIPAIM), pp. 1-5. IEEE, 2023.](https://doi.org/10.1109/SIPAIM56729.2023.10373540)
