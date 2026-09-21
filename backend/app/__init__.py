from importlib.metadata import PackageNotFoundError, version

from app.config import get_settings

try:
    __version__ = version("equity-research-desk")
except PackageNotFoundError:  # running from a source checkout without an install
    __version__ = "0.0.0-dev"

__all__ = ["__version__", "get_settings"]
