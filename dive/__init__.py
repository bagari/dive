"""DiVE — Diffusion Visualization and Explorer."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dive-mri")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
