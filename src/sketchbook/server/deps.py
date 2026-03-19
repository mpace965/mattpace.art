"""FastAPI dependency functions for server route handlers."""

from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates

from sketchbook.server.registry import SketchRegistry


def get_registry(request: Request) -> SketchRegistry:
    """Return the SketchRegistry stored on ``app.state``."""
    return request.app.state.registry


def get_templates(request: Request) -> Jinja2Templates:
    """Return the Jinja2Templates instance stored on ``app.state``."""
    return request.app.state.templates
