"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sketchbook.core.executor import execute, execute_partial
from sketchbook.core.sketch import Sketch
from sketchbook.core.watcher import Watcher
from sketchbook.server.routes import dag as dag_routes
from sketchbook.server.routes import params as params_routes
from sketchbook.server.routes import presets as presets_routes
from sketchbook.server.routes import sketch as sketch_routes
from sketchbook.server.routes import ws as ws_routes
from sketchbook.steps.source import SourceFile

log = logging.getLogger("sketchbook.server")

_templates_dir = Path(__file__).parent / "templates"

# Loaded sketch instances (populated eagerly by tests, lazily by dev server)
_sketches: dict[str, Sketch] = {}

# Unloaded candidates for lazy loading (dev server only)
_candidates: dict[str, type[Sketch]] = {}
_sketch_locks: dict[str, threading.Lock] = {}
_sketches_dir: Path | None = None

# Set during lifespan for lazy watcher registration
_watcher: Watcher | None = None
_loop: asyncio.AbstractEventLoop | None = None

# Sketch IDs that currently have file watchers registered
_watched_sketches: set[str] = set()


def get_watched_sketch_ids() -> frozenset[str]:
    """Return the sketch IDs that currently have file watchers registered."""
    return frozenset(_watched_sketches)


def list_sketch_infos() -> list[dict[str, str]]:
    """Return display metadata for all known sketches (loaded and candidates).

    Draws name, description, and date from class attributes so candidates
    (not yet instantiated) are included without triggering a load.
    """
    infos: list[dict[str, str]] = []
    seen: set[str] = set()

    for sketch_id, sketch in _sketches.items():
        cls = type(sketch)
        infos.append({
            "id": sketch_id,
            "name": cls.name,
            "description": getattr(cls, "description", ""),
            "date": getattr(cls, "date", ""),
        })
        seen.add(sketch_id)

    for sketch_id, cls in _candidates.items():
        if sketch_id not in seen:
            infos.append({
                "id": sketch_id,
                "name": cls.name,
                "description": getattr(cls, "description", ""),
                "date": getattr(cls, "date", ""),
            })

    return sorted(infos, key=lambda x: x["date"], reverse=True)


def _register_watch(watcher: Watcher, sketch_id: str, sketch: Sketch, loop: asyncio.AbstractEventLoop) -> None:
    """Watch all source nodes in a sketch and wire changes to partial re-execution + broadcast."""
    _watched_sketches.add(sketch_id)
    for node in sketch.dag.topo_sort():
        if not isinstance(node.step, SourceFile):
            continue

        source_path = node.step._path
        changed_node_id = node.id

        def on_change(sid: str = sketch_id, sk: Sketch = sketch, nid: str = changed_node_id) -> None:
            log.info(f"Source '{nid}' changed for sketch '{sid}', re-executing descendants")
            result = execute_partial(sk.dag, [nid])
            asyncio.run_coroutine_threadsafe(
                ws_routes.broadcast_results(sid, sk.dag, result),
                loop,
            )

        watcher.watch(source_path, on_change)


def _load_sketch_lazy(sketch_id: str) -> Sketch | None:
    """Instantiate and execute a sketch on first access, then register its file watcher."""
    cls = _candidates[sketch_id]
    if _sketches_dir is None:
        raise RuntimeError("_load_sketch_lazy called before create_app set _sketches_dir")
    sketch_dir = _sketches_dir / sketch_id
    t0 = time.perf_counter()
    try:
        instance = cls(sketch_dir)
        execute(instance.dag)
        elapsed = time.perf_counter() - t0
        log.info(f"Loaded sketch '{sketch_id}': {cls.name} ({elapsed:.2f}s)")
        _sketches[sketch_id] = instance
        if _watcher is not None and _loop is not None:
            _register_watch(_watcher, sketch_id, instance, _loop)
        return instance
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        log.warning(f"Failed to load sketch '{sketch_id}': {exc} ({elapsed:.2f}s)")
        # Remove from candidates so subsequent requests get a clean 404
        # rather than retrying and re-logging the same failure.
        _candidates.pop(sketch_id, None)
        return None


def get_sketch(sketch_id: str) -> Sketch | None:
    """Look up a sketch by ID, loading it lazily on first access if a candidate exists."""
    if sketch_id in _sketches:
        return _sketches[sketch_id]
    if sketch_id not in _candidates:
        return None
    with _sketch_locks[sketch_id]:
        # Double-check after acquiring the lock
        if sketch_id in _sketches:
            return _sketches[sketch_id]
        return _load_sketch_lazy(sketch_id)


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

    Note:
        The app's lifespan starts the file watcher. For eager sketches the watcher is
        registered at startup; for lazy candidates it is registered on first load.
    """
    global _sketches, _candidates, _sketch_locks, _sketches_dir, _watched_sketches
    _sketches = sketches
    _sketches_dir = sketches_dir
    _candidates = candidates or {}
    _sketch_locks = {slug: threading.Lock() for slug in _candidates}
    _watched_sketches = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        global _watcher, _loop
        _loop = asyncio.get_running_loop()
        watcher = Watcher()
        _watcher = watcher
        for sketch_id, sketch in _sketches.items():
            _register_watch(watcher, sketch_id, sketch, _loop)
        watcher.start()
        try:
            yield
        finally:
            watcher.stop()
            _watcher = None
            _loop = None

    app = FastAPI(title="Sketchbook", lifespan=lifespan)

    templates = Jinja2Templates(directory=str(_templates_dir))
    sketch_routes.init_templates(templates)

    app.include_router(sketch_routes.router)
    app.include_router(params_routes.router)
    app.include_router(presets_routes.router)
    app.include_router(ws_routes.router)
    app.include_router(dag_routes.router)

    # Serve .workdir/ output images per sketch.
    # Eager sketches: workdir already exists (sketch was executed).
    # Lazy candidates: pre-create the directory so StaticFiles mount succeeds;
    # it will be populated when the sketch is first loaded.
    all_ids = set(_sketches) | set(_candidates)
    for sketch_id in all_ids:
        if sketch_id in _sketches:
            workdir = _sketches[sketch_id].sketch_dir / ".workdir"
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
