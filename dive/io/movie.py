import vtk
import math
import logging
import numpy as np
import imageio.v3 as iio
from PIL import Image
from vtkmodules.util.numpy_support import vtk_to_numpy

log = logging.getLogger(__name__)

def _downscale(frame, target_size):
    """Lanczos downscale of an oversampled frame for cleaner anti-aliasing."""
    img = Image.fromarray(frame)
    img = img.resize(target_size, Image.LANCZOS)
    return np.asarray(img)

def _set_orbit_camera(scene, axis, theta, cos_e, sin_e, center, distance, parallel_scale):
    """Place the camera on a circle around *center* at angle *theta*."""
    if axis == "yaw":
        # Orbit:axial plane (superior–inferior axis).
        direction = np.array([math.cos(theta) * cos_e, math.sin(theta) * cos_e, sin_e])
        view_up = (0.0, 0.0, 1.0)
    else:
        # Orbit: left–right axis.
        direction = np.array([math.cos(theta), sin_e, math.sin(theta) * cos_e ])
        view_up = (0.0, 1.0, 0.0)

    position = tuple(center + direction * distance)
    scene.set_camera(position=position, focal_point=tuple(center), view_up=view_up)
    if parallel_scale is not None:
        scene.GetActiveCamera().SetParallelScale(parallel_scale)


def record_rotation(scene, output_path, *, axis="yaw",
    duration_s=8.0, fps=30, size=(1920, 1080), loops=1, elevation_deg=0.0,
    cam_center=None, cam_distance=None, parallel_scale=None, hide_actors=()):

    """Render a 360° rotation video and write it to *output_path* as MP4.

    Uses a single persistent offscreen render window for the entire rotation,
    avoiding the per-frame context creation that overwhelms the macOS
    graphics stack on large scenes (the cause of "Context leak detected"
    messages and the OOM kill seen with N>~50 frames + heavy scenes).
    """
    if axis not in ("yaw", "pitch"):
        raise ValueError(f"axis must be 'yaw' or 'pitch', got {axis!r}")
    if not output_path.lower().endswith(".mp4"):
        raise ValueError(f"output_path must end with .mp4, got {output_path!r}")

    # yuv420p requires even dimensions in both axes.
    width, height = size
    width  -= width  % 2
    height -= height % 2
    render_w = (width  * 2) - ((width  * 2) % 2)
    render_h = (height * 2) - ((height * 2) % 2)

    n_frames = max(2, int(round(duration_s * fps))) * loops

    for actor in hide_actors:
        scene.rm(actor)

    if cam_center is None or cam_distance is None:
        scene.reset_camera()
        camera = scene.GetActiveCamera()
        cam_center = np.array(camera.GetFocalPoint(), dtype=float)
        position = np.array(camera.GetPosition(), dtype=float)
        cam_distance = float(np.linalg.norm(position - cam_center)) or 400.0
        parallel_scale = camera.GetParallelScale()
    else:
        cam_center = np.asarray(cam_center, dtype=float)

    log.info("Recording %s rotation: %.1fs × %d loop(s) @ %d fps, %dx%d → %s",
        axis, duration_s, loops, fps, width, height, output_path)

    elevation = math.radians(elevation_deg)
    cos_e = math.cos(elevation)
    sin_e = math.sin(elevation)
    angles = np.linspace(0.0, 2.0 * math.pi * loops, n_frames, endpoint=False)

    render_window = vtk.vtkRenderWindow()
    render_window.SetOffScreenRendering(1)
    render_window.SetMultiSamples(8)
    render_window.AddRenderer(scene)
    render_window.SetSize(render_w, render_h)

    image_filter = vtk.vtkWindowToImageFilter()
    image_filter.SetInput(render_window)
    image_filter.SetInputBufferTypeToRGB()
    image_filter.ReadFrontBufferOff()

    try:
        with iio.imopen(output_path, "w", plugin="pyav") as writer:
            writer.init_video_stream("libx264", fps=fps, pixel_format="yuv420p")
            for theta in angles:
                _set_orbit_camera(scene, axis, theta, cos_e, sin_e, cam_center, cam_distance, parallel_scale)
                render_window.Render()
                image_filter.Modified()
                image_filter.Update()

                vtk_image = image_filter.GetOutput()
                w_dim, h_dim, _ = vtk_image.GetDimensions()
                vtk_arr = vtk_image.GetPointData().GetScalars()
                frame = vtk_to_numpy(vtk_arr).reshape(h_dim, w_dim, -1)
                frame = np.flipud(frame)

                writer.write_frame(_downscale(frame, (width, height)))
    finally:
        render_window.RemoveRenderer(scene)
        render_window.Finalize()
        for actor in hide_actors:
            scene.add(actor)
