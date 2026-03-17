"""Entry points for uv run dev and uv run build."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import pkgutil
from pathlib import Path

import uvicorn

from sketchbook.core.executor import execute
from sketchbook.core.sketch import Sketch
from sketchbook.core.watcher import Watcher

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sketchbook.cli")

_SKETCHES_PACKAGE = "sketchbook.sketches"
_SKETCHES_DIR = Path(__file__).parent / "sketches"


def discover_sketches() -> dict[str, Sketch]:
    """Scan sketchbook.sketches submodules for Sketch subclasses and instantiate them."""
    import sketchbook.sketches  # noqa: F401

    sketches: dict[str, Sketch] = {}

    for mod_info in pkgutil.iter_modules([str(_SKETCHES_DIR)]):
        slug = mod_info.name
        module = importlib.import_module(f"{_SKETCHES_PACKAGE}.{slug}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Sketch) and obj is not Sketch:
                sketch_dir = _SKETCHES_DIR / slug
                try:
                    instance = obj(sketch_dir)
                    execute(instance.dag)
                    sketches[slug] = instance
                    log.info(f"Loaded sketch '{slug}': {obj.name}")
                except Exception as exc:
                    log.warning(f"Skipping sketch '{slug}': {exc}")
                break

    return sketches


def _register_watch(watcher: Watcher, sketch_id: str, sketch: Sketch, loop: asyncio.AbstractEventLoop) -> None:
    """Watch all source nodes in a sketch and wire changes to re-execution + broadcast."""
    from sketchbook.server.routes import ws as ws_routes
    from sketchbook.steps.source import SourceFile

    for node in sketch.dag.topo_sort():
        if not isinstance(node.step, SourceFile):
            continue

        source_path = node.step._path

        def on_change(sid: str = sketch_id, sk: Sketch = sketch) -> None:
            log.info(f"Source changed for sketch '{sid}', re-executing")
            result = execute(sk.dag)
            asyncio.run_coroutine_threadsafe(
                ws_routes.broadcast_results(sid, sk.dag, result),
                loop,
            )

        watcher.watch(source_path, on_change)


def dev() -> None:
    """Start the dev server."""
    from sketchbook.server.app import create_app

    sketches = discover_sketches()
    if not sketches:
        log.warning("No sketches loaded — server will start with no content")

    app = create_app(sketches, sketches_dir=_SKETCHES_DIR)
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, lifespan="off")
    server = uvicorn.Server(config)

    async def serve() -> None:
        loop = asyncio.get_running_loop()
        watcher = Watcher()
        for sketch_id, sketch in sketches.items():
            _register_watch(watcher, sketch_id, sketch, loop)
        watcher.start()
        try:
            await server.serve()
        finally:
            watcher.stop()

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


def build() -> None:
    """Build the static site."""
    raise NotImplementedError("build not yet implemented")
