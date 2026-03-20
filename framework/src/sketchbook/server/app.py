"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sketchbook.core.sketch import Sketch
from sketchbook.server.registry import SketchRegistry
from sketchbook.server.routes import dag as dag_routes
from sketchbook.server.routes import params as params_routes
from sketchbook.server.routes import presets as presets_routes
from sketchbook.server.routes import sketch as sketch_routes
from sketchbook.server.routes import ws as ws_routes

log = logging.getLogger("sketchbook.server")

_templates_dir = Path(__file__).parent / "templates"


def create_app(
    sketches: dict[str, Sketch],
    sketches_dir: Path | None = None,
    *,
    candidates: dict[str, type[Sketch]] | None = None,
) -> FastAPI:
    """Build and return the FastAPI app with all routes mounted.

    Args:
        sketches: Already-built sketch instances (used by tests; immediately available).
        sketches_dir: Root directory containing sketch modules (for workdir serving).
        candidates: Uninstantiated Sketch subclasses for lazy loading (dev server path).
            When provided, sketches are instantiated and executed on first request.
    """
    registry = SketchRegistry(sketches, sketches_dir, candidates=candidates)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        loop = asyncio.get_running_loop()
        registry.start_watcher(loop)
        try:
            yield
        finally:
            registry.stop_watcher()

    app = FastAPI(title="Sketchbook", lifespan=lifespan)
    app.state.registry = registry
    app.state.templates = Jinja2Templates(directory=str(_templates_dir))

    app.include_router(sketch_routes.router)
    app.include_router(params_routes.router)
    app.include_router(presets_routes.router)
    app.include_router(ws_routes.router)
    app.include_router(dag_routes.router)

    # Serve .workdir/ output images per sketch.
    # Eager sketches: workdir already exists (sketch was executed).
    # Lazy candidates: pre-create the directory so StaticFiles mount succeeds;
    # it will be populated when the sketch is first loaded.
    all_ids = set(sketches) | set(registry.candidates)
    for sketch_id in all_ids:
        if sketch_id in sketches:
            workdir = sketches[sketch_id].sketch_dir / ".workdir"
        else:
            assert sketches_dir is not None
            workdir = sketches_dir / sketch_id / ".workdir"
            workdir.mkdir(parents=True, exist_ok=True)
        app.mount(
            f"/workdir/{sketch_id}",
            StaticFiles(directory=str(workdir)),
            name=f"workdir_{sketch_id}",
        )

    return app
