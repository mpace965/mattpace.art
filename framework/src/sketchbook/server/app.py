"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from sketchbook.server.fn_registry import SketchFnRegistry
from sketchbook.server.routes import sketches as sketch_routes

log = logging.getLogger("sketchbook.server")

_templates_dir = Path(__file__).parent / "templates"


def create_app(fn_registry: SketchFnRegistry) -> FastAPI:
    """Build and return the FastAPI app with sketch routes mounted.

    Args:
        fn_registry: The SketchFnRegistry backing all routes.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        loop = asyncio.get_running_loop()
        fn_registry.start_watcher(loop)
        try:
            yield
        finally:
            fn_registry.stop_watcher()

    app = FastAPI(title="Sketchbook", lifespan=lifespan)
    app.state.fn_registry = fn_registry
    app.state.templates = Jinja2Templates(directory=str(_templates_dir))
    app.include_router(sketch_routes.router)

    return app
