"""Dev app factory — called by uvicorn's reload worker on each restart.

Uvicorn reload mode requires the app to be specified as an importable factory
rather than a pre-built object.  This module provides that entry point.
"""

from __future__ import annotations

from fastapi import FastAPI

from sketchbook.cli import _SKETCHES_DIR
from sketchbook.discovery import discover_sketch_fns, discover_sketches
from sketchbook.server.app import create_app
from sketchbook.server.fn_registry import SketchFnRegistry


def create_dev_app() -> FastAPI:
    """Discover sketch classes and functions, build the FastAPI app for the dev server.

    Old-style Sketch subclasses and new-style @sketch functions are both discovered
    and served. Neither is instantiated or executed here — that happens lazily on
    first request so the server starts immediately.
    """
    candidates = discover_sketches(_SKETCHES_DIR)
    sketch_fns = discover_sketch_fns(_SKETCHES_DIR)
    fn_registry = (
        SketchFnRegistry(sketch_fns, sketches_dir=_SKETCHES_DIR) if sketch_fns else None
    )
    return create_app(
        {}, sketches_dir=_SKETCHES_DIR, candidates=candidates, fn_registry=fn_registry
    )
