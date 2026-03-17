"""Entry points for uv run dev and uv run build."""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path

import uvicorn

from sketchbook.core.executor import execute
from sketchbook.core.sketch import Sketch

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


def dev() -> None:
    """Start the dev server."""
    from sketchbook.server.app import create_app

    sketches = discover_sketches()
    if not sketches:
        log.warning("No sketches loaded — server will start with no content")

    app = create_app(sketches, sketches_dir=_SKETCHES_DIR)
    uvicorn.run(app, host="127.0.0.1", port=8000)


def build() -> None:
    """Build the static site."""
    raise NotImplementedError("build not yet implemented")
