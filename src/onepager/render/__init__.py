"""Rendering layer: theme, components, and the one-page layout engine."""

from .onepager import RenderError, RenderReport, plan, render

__all__ = ["RenderError", "RenderReport", "plan", "render"]
