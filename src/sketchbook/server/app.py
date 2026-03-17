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

from sketchbook.core.executor import execute
from sketchbook.core.sketch import Sketch
from sketchbook.core.watcher import Watcher
from sketchbook.server.routes import sketch as sketch_routes
from sketchbook.server.routes import ws as ws_routes
from sketchbook.steps.source import SourceFile

log = logging.getLogger("sketchbook.server")

_sketches: dict[str, Sketch] = {}
_templates_dir = Path(__file__).parent / "templates"


def create_app(sketches: dict[str, Sketch], sketches_dir: Path | None = None) -> FastAPI:
    """Build and return the FastAPI app with all routes mounted.

    Args:
        sketches: mapping of sketch_id -> Sketch instance, already built and executed.
        sketches_dir: root directory containing sketch modules (for workdir serving).
    """
    global _sketches
    _sketches = sketches

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        loop = asyncio.get_running_loop()
        watcher = Watcher()

        for sketch_id, sketch in sketches.items():
            _register_watch(watcher, sketch_id, sketch, loop)

        watcher.start()
        yield
        watcher.stop()

    app = FastAPI(title="Sketchbook", lifespan=lifespan)

    templates = Jinja2Templates(directory=str(_templates_dir))
    sketch_routes.init_templates(templates)

    app.include_router(sketch_routes.router)
    app.include_router(ws_routes.router)

    # Serve .workdir/ output images per sketch
    for sketch_id, sketch in sketches.items():
        workdir = sketch.sketch_dir / ".workdir"
        app.mount(
            f"/workdir/{sketch_id}",
            StaticFiles(directory=str(workdir)),
            name=f"workdir_{sketch_id}",
        )

    return app


def _register_watch(watcher: Watcher, sketch_id: str, sketch: Sketch, loop: asyncio.AbstractEventLoop) -> None:
    """Watch all source nodes in a sketch and wire changes to re-execution + broadcast."""
    for node in sketch.dag.topo_sort():
        if not isinstance(node.step, SourceFile):
            continue

        source_path = node.step._path

        def on_change(sid: str = sketch_id, sk: Sketch = sketch) -> None:
            log.info(f"Source changed for sketch '{sid}', re-executing")
            result = execute(sk.dag)
            for n in sk.dag.topo_sort():
                if not n.workdir_path:
                    continue
                if n.id in result.errors:
                    asyncio.run_coroutine_threadsafe(
                        ws_routes.broadcast(sid, {
                            "type": "step_error",
                            "step_id": n.id,
                            "error": str(result.errors[n.id]),
                        }),
                        loop,
                    )
                else:
                    asyncio.run_coroutine_threadsafe(
                        ws_routes.broadcast(sid, {
                            "type": "step_updated",
                            "step_id": n.id,
                            "image_url": f"/workdir/{sid}/{n.id}.png",
                        }),
                        loop,
                    )

        watcher.watch(source_path, on_change)


def get_sketch(sketch_id: str) -> Sketch | None:
    """Look up a loaded sketch by ID."""
    return _sketches.get(sketch_id)
