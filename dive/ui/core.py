import os
import sys
import logging
import re
import vtk
import subprocess
import numpy as np
from enum import IntEnum
from importlib.resources import files
from fury import ui, window
from vtkmodules.vtkCommonColor import vtkNamedColors

from dive.utils.color import parse_color
from dive.io.movie import record_rotation
from meta.io.transform import load_transformation
from dive.core.scene import load_scene_objects
import dive.ui as _ui
from dive.ui.containers import Panel2D
from dive.ui.elements import ComboBox2D, Option, RadioButton, LineSlider2D

log = logging.getLogger(__name__)

_ASSETS = files("dive").joinpath("assets")
_ICON_MINUS = str(_ASSETS.joinpath("minus.png"))
_ICON_ADD = str(_ASSETS.joinpath("add.png"))

class Orientation(IntEnum):
    SAGITTAL = 1
    AXIAL    = 2
    CORONAL  = 3

class Show:

    def __init__(self, background, zoom=1.0):
        self.background = background
        self.zoom = zoom

        self.scene = None
        self.slice_actor = None
        self.brain_2d = None
        self.max_value_view = None

        self.selected_actor = _ui.selected_item

        # Cache for camera — populated by cache_camera_center_and_distance()
        self.cam_center = None      # (cx, cy, cz)
        self.cam_distance = None    # scalar
        self.cam_par_scale = None   # ParallelScale at reset_camera() time

        # self.ori = 1
        self.ori = Orientation.SAGITTAL
        self.slider_cut = None
        self.rois = None
        self._add_count = 0
        


    # ------------------------------------------------------------------
    # Scene setup
    # ------------------------------------------------------------------

    def build_scene(self):
        """Create and return the FURY window scene."""
        colors = vtkNamedColors()
        self.scene = window.Scene()
        if self.background == 1:
            self.scene.SetBackground(colors.GetColor3d("White"))

        # Parallel (orthographic) projection — no perspective distortion when
        # sliding the slice, and consistent with the saved-PNG output.
        self.scene.GetActiveCamera().SetParallelProjection(True)

        # Default: Sagittal_R view (distance only sets direction in parallel mode)
        self.scene.set_camera(position=(400.0, 0, 0), focal_point=(0, 0, 0), view_up=(0, 0, 1))

        return self.scene


    def set_max_view(self, maxval=180, slice_actor=None, brain_2d=None):
        self.max_value_view = maxval
        self.slice_actor = slice_actor
        self.brain_2d = brain_2d


    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def cache_camera_center_and_distance(self):
        """Cache focal point, distance, and parallel scale after reset_camera()."""
        cam = self.scene.GetActiveCamera()
        f = np.array(cam.GetFocalPoint(), dtype=float)
        p = np.array(cam.GetPosition(), dtype=float)
        self.cam_center = tuple(f)
        self.cam_distance = float(np.linalg.norm(p - f)) or 400.0
        self.cam_par_scale = cam.GetParallelScale()


    def set_fury_camera(self, scene, view='Axial_I'):
        """
        Apply a predefined camera orientation.

        Uses the cached center/distance from reset_camera() when available;
        falls back to a fixed 400-unit distance otherwise.

        Supported views: Sagittal_L, Sagittal_R, Coronal_A, Coronal_P,
                         Axial_S (from superior), Axial_I (from inferior),
                         Axial (alias for Axial_I, used by CLI --cam_view).
        """
        # Direction unit-vectors: where the camera sits relative to the centre
        dir_map = {
            'Sagittal_L': np.array([-1.0, 0.0, 0.0]),    # from left
            'Sagittal_R': np.array([ 1.0, 0.0, 0.0]),    # from right
            'Coronal_A': np.array([ 0.0, 1.0, 0.0]),    # from anterior (front)
            'Coronal_P': np.array([ 0.0, -1.0, 0.0]),    # from posterior (behind)
            'Axial_S': np.array([ 0.0, 0.0, 1.0]),    # from superior (above)
            'Axial_I': np.array([ 0.0, 0.0, -1.0]),    # from inferior (below)
        }
        up_map = {'Sagittal_L': (0, 0, 1), 'Sagittal_R': (0, 0, 1),
            'Coronal_A': (0, 0, 1), 'Coronal_P': (0, 0, 1),
            'Axial_S': (0, 1, 0), 'Axial_I': (0, 1, 0)}

        direction = dir_map.get(view, dir_map['Axial_I'])
        direction = direction / np.linalg.norm(direction)
        view_up   = up_map.get(view, (0, 1, 0))

        # Position the camera (direction only; distance has no visual effect in
        # parallel projection — zoom is handled separately via ParallelScale).
        if self.cam_center is None or self.cam_distance is None:
            scene.set_camera(position=tuple(direction * 400.0), focal_point=(0, 0, 0), view_up=view_up)
        else:
            center = np.array(self.cam_center, dtype=float)
            scene.set_camera(position=tuple(center + direction * self.cam_distance), focal_point=tuple(center), view_up=view_up)

        # Zoom: smaller ParallelScale = more zoomed in. This is an absolute set
        # so it is idempotent — calling set_fury_camera repeatedly is safe.
        if self.cam_par_scale is not None:
            scene.GetActiveCamera().SetParallelScale(self.cam_par_scale / self.zoom)


    # ------------------------------------------------------------------
    # CLI output
    # ------------------------------------------------------------------

    def save_results(self, output_path, views=None):
        """Save a PNG screenshot for each requested camera view."""
        self.scene.reset_camera()
        camera = self.scene.GetActiveCamera()
        camera.SetParallelScale(150)    # explicit scale for consistent output size
        # cache after setting scale so set_fury_camera picks up 150 (÷ zoom)
        self.cache_camera_center_and_distance()

        for view in views:
            self.set_fury_camera(self.scene, view)
            camera.SetClippingRange(0.1, 2000)

            if self.slice_actor:
                if view in ('Sagittal_L', 'Sagittal_R'):
                    cut = int(self.brain_2d[0]) if self.brain_2d else self.slice_actor.shape[0] // 2
                    self.slice_actor.display(x=cut, y=None, z=None)
                elif view in ('Coronal_A', 'Coronal_P'):
                    cut = int(self.brain_2d[1]) if self.brain_2d else self.slice_actor.shape[1] // 2
                    self.slice_actor.display(x=None, y=cut, z=None)
                elif view in ('Axial_S', 'Axial_I'):
                    cut = int(self.brain_2d[2]) if self.brain_2d else self.slice_actor.shape[2] // 2
                    self.slice_actor.display(x=None, y=None, z=cut)

            if os.path.isdir(output_path):
                fname = os.path.join(output_path, f"{view}.png")
            else:
                fname = f"{output_path}_{view}.png"
            window.record(scene=self.scene, out_path=fname, size=(2000, 2000), reset_camera=False)
            log.info("Saved: %s", fname)

    def record_rotation_movie(self, output_path, *, axis="yaw", duration_s=8.0,
                            fps=30, size=(1920, 1080), loops=1, elevation_deg=0.0, hide_slice=True):
        """Render a rotating-brain video using the current scene + camera.

        Honors any pre-existing camera framing: only auto-frames when no camera
        has been cached yet (e.g. movie mode invoked directly with no GUI step).
        """
        if self.cam_center is None:
            self.scene.reset_camera()
            self.cache_camera_center_and_distance()

        hide = (self.slice_actor,) if (hide_slice and self.slice_actor) else ()
        record_rotation(
            self.scene, output_path,
            axis=axis, duration_s=duration_s, fps=fps, size=size,
            loops=loops, elevation_deg=elevation_deg,
            cam_center=self.cam_center,
            cam_distance=self.cam_distance,
            parallel_scale=self.cam_par_scale,
            hide_actors=hide,
        )
    # ------------------------------------------------------------------
    # GUI panel
    # ------------------------------------------------------------------

    def build_label(self, text, title=False):
        """
        Args:
            text:  str  – text to display
            title: bool – larger, bold font when True
        Returns:
            FURY TextBlock2D actor
        """
        label = ui.TextBlock2D()
        label.message = text
        label.font_size = 18
        label.font_family = 'Arial'
        label.justification = 'left'
        label.bold = False
        label.italic = False
        label.shadow = False
        label.color = (0, 0, 0)
        if title:
            label.font_size = 20
            label.bold = True
        return label


    def _layout_panel(self):
        self.panel.add_element(self.view, (0.1, 0.05))
        self.panel.add_element(self.flipper, (0.5, 0.09))
        self.panel.add_element(self.combox_mask, (0.1, 0.65))
        self.panel.add_element(self.combox_track, (0.1, 0.55))
        self.panel.add_element(self.combox_mesh, (0.1, 0.45))
        self.panel.add_element(self.combox_brain, (0.1, 0.35))
        self.panel.add_element(self.slice_slider_label, (0.2, 0.53))
        self.panel.add_element(self.slice_slider, (0.55, 0.53))
        self.panel.add_element(self.remove_button, (0.5, 0.4))
        self.panel.add_element(self.add_button, (0.1, 0.4))
        self.panel.add_element(self.opacity_slider_label,(0.1, 0.3))
        self.panel.add_element(self.opacity_slider, (0.55, 0.3))


    # ------------------------------------------------------------------
    # GUI interactions
    # ------------------------------------------------------------------

    def change_view(self, radio):
        """
        Args:
            radio: RadioButton – triggers on label change
        Sets the orientation and moves the camera to the default (unflipped) view.
        """
        # Map radio label → (self.ori, set_fury_camera view name)
        label_map = {
            "Sagittal": (Orientation.SAGITTAL, "Sagittal_R"),
            "Axial": (Orientation.AXIAL, "Axial_I"),
            "Coronal": (Orientation.CORONAL, "Coronal_A"),
        }
        self.ori, view = label_map[radio.checked_labels[0]]
        self.flipper.deselect()
        self.selected_actor = self.slice_actor

        # 1. Reposition the slice FIRST so reset_camera() sees the correct scene layout
        if self.slice_actor:
            self.slice_actor.GetProperty().SetOpacity(1)
            self.scene.rm(self.slice_actor)
            if self.ori == Orientation.SAGITTAL:
                cut = int(self.brain_2d[0]) if self.brain_2d else self.slice_actor.shape[0] // 2
                if self.slider_cut is not None:
                    cut = self.slider_cut
                self.slice_actor.display(x=cut, y=None, z=None)
            elif self.ori == Orientation.AXIAL:
                cut = int(self.brain_2d[2]) if self.brain_2d else self.slice_actor.shape[2] // 2
                if self.slider_cut is not None:
                    cut = self.slider_cut
                self.slice_actor.display(x=None, y=None, z=cut)
            elif self.ori == Orientation.CORONAL:
                cut = int(self.brain_2d[1]) if self.brain_2d else self.slice_actor.shape[1] // 2
                if self.slider_cut is not None:
                    cut = self.slider_cut
                self.slice_actor.display(x=None, y=cut, z=None)
            self.scene.add(self.slice_actor)

        # 2. Now cache center/distance from the correctly positioned scene
        self.scene.reset_camera()
        self.cache_camera_center_and_distance()
        self.set_fury_camera(self.scene, view)


    def flip_view(self, option):
        """Toggle between the two opposing camera directions for the active orientation."""
        view_map = {
            (1, False): 'Sagittal_R',
            (1, True):  'Sagittal_L',
            (2, False): 'Axial_I',
            (2, True):  'Axial_S',
            (3, False): 'Coronal_A',
            (3, True):  'Coronal_P',
        }
        view = view_map.get((self.ori, bool(self.flipper.checked)), 'Axial_I')
        self.set_fury_camera(self.scene, view)


    def change_slice_handler(self, slider):
        self.slider_cut = int(slider.value)
        self.scene.rm(self.slice_actor)
        if self.ori == Orientation.SAGITTAL:
            self.slice_actor.display(x=self.slider_cut, y=None, z=None)
        elif self.ori == Orientation.AXIAL:
            self.slice_actor.display(x=None, y=None, z=self.slider_cut)
        elif self.ori == Orientation.CORONAL:
            self.slice_actor.display(x=None, y=self.slider_cut, z=None)
        self.scene.add(self.slice_actor)


    def interact_selected_actor(self):
        if _ui.selected_item is None or _ui.selected_item not in self.rois:
            return
        self.selected_actor = self.rois[_ui.selected_item]


    def change_opacity(self, slider):
        if _ui.selected_item is None or _ui.selected_item not in self.rois:
            return
        self.selected_actor = self.rois[_ui.selected_item]
        if isinstance(self.selected_actor, vtk.vtkAssembly):
            opacity = slider.value
            for i in range(self.selected_actor.GetParts().GetNumberOfItems()):
                self.selected_actor.GetParts().GetItemAsObject(i).GetProperty().SetOpacity(opacity)
        else:
            self.selected_actor.GetProperty().SetOpacity(slider.value)


    # ------------------------------------------------------------------
    # Dynamic element loading
    # ------------------------------------------------------------------

    def _parse_command(self, command: str) -> dict:
        """Parse a Viz_UI command string into load_scene_objects kwargs."""

        def findall(flag: str) -> list[str]:
            return re.findall(rf'--{flag}\s(.*?)(?=\s--|$)', command)

        def flat(lst: list[str]) -> list[str]:
            return [item for sub in lst for item in sub.split()]

        def parse_colors(raw: list[str]) -> list:
            joined = " ".join(raw)
            return [parse_color(c) for c in joined.split()] if joined else []

        def one_float(flag):
            hits = re.findall(rf'--{flag}\s(\S+)', command)
            return float(hits[0]) if hits else None

        def one_str(flag):
            hits = re.findall(rf'--{flag}\s(\S+)', command)
            return hits[0] if hits else None

        def one_int(flag):
            hits = re.findall(rf'--{flag}\s(\S+)', command)
            return int(hits[0]) if hits else None

        masks = flat(findall('mask'))
        tracts = flat(findall('tract'))
        meshes = flat(findall('mesh'))

        line_width = findall('tract_width')
        vr = findall('value_range')
        th = findall('threshold')

        # Opacities: viz_ui emits a single value → expand to one entry per file
        mask_op = one_float('mask_opacity')
        tract_op = one_float('tract_opacity')
        mesh_op = one_float('mesh_opacity')

        return dict(
            masks = masks, tracts = tracts, meshes = meshes,
            mask_colors = parse_colors(findall('mask_colors')),
            tract_colors = parse_colors(findall('tract_colors')),
            mesh_colors = parse_colors(findall('mesh_colors')),
            mask_opacity = [mask_op] * len(masks) if mask_op is not None else [],
            tract_opacity = [tract_op] * len(tracts) if tract_op is not None else [],
            mesh_opacity = [mesh_op] * len(meshes) if mesh_op is not None else [],
            stats_csv = flat(findall('stats_csv')),
            colormap = " ".join(findall('map')) or 'RdBu',
            value_range = [float(v) for v in vr[0].split()] if vr else None,
            threshold = float(th[0]) if th else 0.05,
            log_p_value = bool(findall('log_p_value')),
            tract_width = int(line_width[0]) if line_width else 1,
            segmentation_method = one_str('seg_method'),
            num_segments = one_int('num_segments'),
            transform = one_str('transform'),
            inverse = '--inverse' in command.split(),
            warp = one_str('warp'),
            warp_ref = one_str('warp_ref'),
            warp_source = one_str('warp_source') or 'dsi_studio',
            warp_first = '--warp_first' in command.split(),
        )

    def adding_elements(self, command: str):
        """Load objects from a Viz_UI command string and add them to the scene."""
        params   = self._parse_command(command)
        new_rois = load_scene_objects(**params)

        for name, actor in new_rois.items():
            self.show_m.scene.add(actor)
            self.rois[name] = actor

            # Route to the correct combobox by file extension
            ext = os.path.splitext(name)[-1].lower()
            if ext in ('.nii', '.gz'):
                self.combox_mask.append_item([name])
            elif ext in ('.vtk', '.obj', '.stl', '.ply'):
                self.combox_mesh.append_item([name])
            else:
                # .trk / .tck / .trx / .tt and TRX group sub-actors
                self.combox_track.append_item([name])

        self._add_count += 1


    def add_element(self, option):
        try:
            result = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), 'viz_ui.py')],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            self.adding_elements(result.stdout)

        except subprocess.CalledProcessError as e:
            log.error("subprocess stderr: %s", e.stderr)
            log.error("subprocess stdout: %s", e.stdout)


    def remove_element(self, option):
        if _ui.selected_item in self.combox_mesh.items:
            remove_combo_box = self.combox_mesh
        elif _ui.selected_item in self.combox_mask.items:
            remove_combo_box = self.combox_mask
        elif _ui.selected_item in self.combox_track.items:
            remove_combo_box = self.combox_track
        else:
            return

        self.selected_actor = self.rois[_ui.selected_item]
        remove_combo_box.remove_item(_ui.selected_item)
        self.show_m.scene.rm(self.selected_actor)


    def interaction(self):
        self.opacity_slider.on_change = self.change_opacity
        self.view.on_change = self.change_view
        self.flipper.on_change = self.flip_view
        self.slice_slider.on_change = self.change_slice_handler
        self.remove_button.on_change = self.remove_element
        self.add_button.on_change = self.add_element


    # ------------------------------------------------------------------
    # Show manager
    # ------------------------------------------------------------------
    def init_show_manager(
        self,
        display_groups,
        rois,
        mode,
        camera_view,
        output_path,
        *,
        movie_axis="yaw",
        movie_duration=8.0,
        movie_fps=30,
        movie_size="1920x1080",
        movie_loops=1,
        movie_elevation=0.0,
        movie_show_slice=False,
    ):

        self.size_screen = (1600, 1300)
        self.show_m = window.ShowManager(
            scene=self.scene,
            title="DiVE — Diffusion Visualization and Explorer | LoBeS",
            size=self.size_screen,
        )

        # CLI mode: save screenshots
        if mode == "cli":
            self.save_results(output_path, views=camera_view)
            return
    
        # movie mode
        if mode == "movie":
            if not output_path:
                raise ValueError("--output is required for --mode movie")
            out = output_path if output_path.lower().endswith(".mp4") else f"{output_path}.mp4"
            width, height = (int(v) for v in movie_size.lower().split("x"))
            self.record_rotation_movie(output_path=out, axis=movie_axis,
                duration_s=movie_duration, fps=movie_fps,
                size=(width, height), loops=movie_loops,
                elevation_deg=movie_elevation,
                hide_slice=not movie_show_slice)
            return

        # interactive mode
        self.slice_slider_label = self.build_label(text="Slice")
        self.opacity_slider_label = self.build_label(text="Opacity")
        self.remove_button = Option("Remove", icon=_ICON_MINUS)
        self.add_button = Option("Add", icon=_ICON_ADD)

        if self.max_value_view is None:
            self.max_value_view = 180

        self.slice_slider = LineSlider2D(
            min_value=0, max_value=self.max_value_view,
            initial_value=0, length=100, text_template="{value:.0f}",
        )
        self.opacity_slider = LineSlider2D(
            min_value=0.0, max_value=1, initial_value=1,
            length=100, text_template="{value:.1f}",
        )

        self.combox_brain = ComboBox2D(
            items=display_groups["Brain"], placeholder="Brain: ", size=(290, 150),
            others=[self.slice_slider, self.slice_slider_label,
                    self.add_button, self.remove_button,
                    self.opacity_slider_label, self.opacity_slider],
        )
        self.combox_mesh = ComboBox2D(
            items=display_groups["Mesh"], placeholder="Mesh: ", size=(290, 150),
            others=[self.combox_brain, self.slice_slider, self.slice_slider_label],
        )
        self.combox_track = ComboBox2D(
            items=display_groups["Tract"], placeholder="Tract: ", size=(290, 150),
            others=[self.combox_brain, self.combox_mesh,
                    self.slice_slider, self.slice_slider_label],
        )
        self.combox_mask = ComboBox2D(
            items=display_groups["Mask"], placeholder="Mask: ", size=(290, 150),
            others=[self.combox_brain, self.combox_track, self.combox_mesh],
        )

        self.rois = rois
        self.panel = Panel2D(size=(300, 400), color=(0.9, 0.9, 0.9), opacity=1, align="left")
        self.view = RadioButton(["Axial", "Coronal", "Sagittal"], checked_labels=["Sagittal"])
        self.flipper = Option("Flipped")

        self._layout_panel()
        self.interaction()

        if self.slice_actor:
            cut = int(self.brain_2d[0]) if self.brain_2d else self.slice_actor.shape[0] // 2
            self.slice_actor.display(x=cut, y=None, z=None)
        self.scene.reset_camera()
        self.cache_camera_center_and_distance()
        self.set_fury_camera(self.scene, "Sagittal_R")

        self.show_m.scene.add(self.panel)
        self.show_m.render()
        self.show_m.start(multithreaded=True)
