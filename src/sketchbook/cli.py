"""Entry points for uv run dev and uv run build."""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import sys
import time
import types
from pathlib import Path

import uvicorn

from sketchbook.core.sketch import Sketch

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sketchbook.cli")

_REPO_ROOT = Path(__file__).parent.parent.parent
_SKETCHES_PACKAGE = "sketches"
_SKETCHES_DIR = _REPO_ROOT / "sketches"


def _find_sketch_class_in_module(module: types.ModuleType) -> type[Sketch] | None:
    """Return the first Sketch subclass found in module, or None."""
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, Sketch) and obj is not Sketch:
            return obj
    return None


def discover_sketch_classes() -> dict[str, type[Sketch]]:
    """Scan sketches/ submodules for Sketch subclasses.

    Only imports modules and collects classes — does not instantiate or execute.
    Instantiation and DAG execution happen lazily on first request.
    """
    repo_root = str(_REPO_ROOT)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    import sketches  # noqa: F401

    t0 = time.perf_counter()
    candidates: dict[str, type[Sketch]] = {}
    for mod_info in pkgutil.iter_modules([str(_SKETCHES_DIR)]):
        slug = mod_info.name
        module = importlib.import_module(f"{_SKETCHES_PACKAGE}.{slug}")
        cls = _find_sketch_class_in_module(module)
        if cls is not None:
            candidates[slug] = cls
    log.info(f"Discovered {len(candidates)} sketch modules in {time.perf_counter() - t0:.2f}s")
    return candidates


def dev() -> None:
    """Start the dev server with hot-reload for framework, template, and sketch code.

    Uvicorn's reload mode watches src/ and sketches/ for .py and .html changes,
    restarting the server worker on any modification.  Source-image watching
    (for pipeline re-execution) is handled by the FastAPI lifespan inside the
    reloaded worker.
    """
    src_dir = _REPO_ROOT / "src"
    uvicorn.run(
        "sketchbook.server._dev:create_dev_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(src_dir), str(_SKETCHES_DIR)],
        reload_includes=["*.py", "*.html"],
    )


def serve() -> None:
    """Serve dist/ as a static site on localhost:8080."""
    import http.server
    import os

    dist_dir = _REPO_ROOT / "dist"
    if not dist_dir.exists():
        print(f"dist/ not found at {dist_dir} — run 'uv run build' first")
        return

    os.chdir(dist_dir)
    port = 8080
    handler = http.server.SimpleHTTPRequestHandler
    with http.server.HTTPServer(("0.0.0.0", port), handler) as httpd:
        print(f"Serving {dist_dir} at http://0.0.0.0:{port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


def build() -> None:
    """Build the static site into dist/."""
    from sketchbook.site.builder import build_site

    sketch_classes = discover_sketch_classes()
    dist_dir = _REPO_ROOT / "dist"
    log.info(f"Building site for {len(sketch_classes)} sketch(es) -> {dist_dir}")
    build_site(sketch_classes, _SKETCHES_DIR, dist_dir)
    print(f"Built {len(sketch_classes)} sketch(es) -> {dist_dir}")
