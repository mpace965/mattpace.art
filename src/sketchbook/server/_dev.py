"""Dev app factory — called by uvicorn's reload worker on each restart.

Uvicorn reload mode requires the app to be specified as an importable factory
rather than a pre-built object.  This module provides that entry point.
"""

from __future__ import annotations

from fastapi import FastAPI

from sketchbook.cli import _SKETCHES_DIR, discover_sketches
from sketchbook.server.app import create_app


def create_dev_app() -> FastAPI:
    """Discover sketches and build the FastAPI app for the dev server."""
    sketches = discover_sketches()
    return create_app(sketches, sketches_dir=_SKETCHES_DIR)
