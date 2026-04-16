"""Dev app factory — called by uvicorn's reload worker on each restart.

Uvicorn reload mode requires the app to be specified as an importable factory
rather than a pre-built object.  This module provides that entry point.
"""

from __future__ import annotations

from fastapi import FastAPI

from sketchbook.cli import _SKETCHES_DIR
from sketchbook.discovery import discover_sketch_fns
from sketchbook.server.app import create_app
from sketchbook.server.fn_registry import SketchFnRegistry


def create_dev_app() -> FastAPI:
    """Discover @sketch functions and build the FastAPI app for the dev server."""
    sketch_fns = discover_sketch_fns(_SKETCHES_DIR)
    fn_registry = SketchFnRegistry(sketch_fns, sketches_dir=_SKETCHES_DIR)
    return create_app(fn_registry)
