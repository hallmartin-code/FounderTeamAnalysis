"""Web layer: a thin HTTP wrapper over the same extract -> analyze -> render pipeline."""

from .app import create_app

__all__ = ["create_app"]
