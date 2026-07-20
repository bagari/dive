import vtk
import pyvista as pv
from fury import utils

def _mesh_property(color=None, opacity=1.0):
    """Return a vtkProperty with the given color and opacity."""
    prop = vtk.vtkProperty()
    if color is not None:
        prop.SetColor(*color)
    prop.SetOpacity(float(opacity))
    prop.SetRoughness(0.0)
    return prop


def load_mesh(polydata_path, color=None, opacity=1.0):
    """Load a VTK PolyData mesh from file and return a vtkActor.

    Parameters
    ----------
    polydata_path : str
        Path to a mesh file supported by PyVista (e.g. .vtk).
    color : tuple of float, optional
        RGB color (0–1). Defaults to the VTK default if None.
    opacity : float
        Actor opacity in [0, 1].

    Returns
    -------
    vtkActor
    """
    poly = pv.PolyData(polydata_path)
    mesh_actor = utils.get_actor_from_polydata(poly)
    mesh_actor.SetProperty(_mesh_property(color=color, opacity=opacity))
    return mesh_actor
