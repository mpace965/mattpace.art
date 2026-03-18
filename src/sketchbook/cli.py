"""Entry points for uv run dev and uv run build."""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import sys
from pathlib import Path

import uvicorn

from sketchbook.core.executor import execute
from sketchbook.core.sketch import Sketch

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sketchbook.cli")

_REPO_ROOT = Path(__file__).parent.parent.parent
_SKETCHES_PACKAGE = "sketches"
_SKETCHES_DIR = _REPO_ROOT / "sketches"


def discover_sketches() -> dict[str, Sketch]:
    """Scan sketches/ submodules for Sketch subclasses and instantiate them."""
    repo_root = str(_REPO_ROOT)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    import sketches  # noqa: F401

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
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(src_dir), str(_SKETCHES_DIR)],
        reload_includes=["*.py", "*.html"],
    )


def build() -> None:
    """Build the static site."""
    raise NotImplementedError("build not yet implemented")
