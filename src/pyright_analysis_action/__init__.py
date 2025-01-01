import os

from .action import app

__version__ = os.getenv("VERSION", "0.1.0dev0")

__all__ = ["app"]
