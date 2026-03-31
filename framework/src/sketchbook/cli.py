"""Entry points for uv run dev, uv run build, and uv run new-sketch."""

from __future__ import annotations

import logging
from pathlib import Path

import uvicorn

from sketchbook.discovery import discover_sketches

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sketchbook.cli")

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_SKETCHES_DIR = _REPO_ROOT / "sketches"


def dev() -> None:
    """Start the dev server with hot-reload for framework, template, and sketch code.

    Uvicorn's reload mode watches src/ and sketches/ for .py and .html changes,
    restarting the server worker on any modification.  Source-image watching
    (for pipeline re-execution) is handled by the FastAPI lifespan inside the
    reloaded worker.
    """
    src_dir = _REPO_ROOT / "src"
    port = 8000
    log.info(f"Dev server: http://localhost:{port}")
    uvicorn.run(
        "sketchbook.server._dev:create_dev_app",
        factory=True,
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=[str(src_dir), str(_SKETCHES_DIR)],
        reload_includes=["*.py", "*.html"],
    )


def build() -> None:
    """Build an output bundle into the output directory.

    Usage: uv run build [--bundle NAME] [--output DIR]

    Defaults to bundle 'bundle' written to sketches/bundle/.
    """
    import argparse

    from sketchbook.site.builder import build_bundle

    parser = argparse.ArgumentParser(prog="build")
    parser.add_argument("--bundle", default="bundle", help="Bundle name to build (default: bundle)")
    parser.add_argument(
        "--output",
        default=str(_SKETCHES_DIR / "bundle"),
        help="Output directory (default: sketches/bundle/)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    sketch_classes = discover_sketches(_SKETCHES_DIR)
    n = len(sketch_classes)
    log.info(f"Building bundle '{args.bundle}' for {n} sketch(es) -> {output_dir}")
    build_bundle(sketch_classes, _SKETCHES_DIR, output_dir, args.bundle)
    print(f"Built bundle '{args.bundle}' with {n} sketch(es) -> {output_dir}")


def new_sketch() -> None:
    """Scaffold a new sketch directory.

    Usage: uv run new-sketch <name>

    Creates sketches/<name>/ with __init__.py, assets/, and presets/_active.json.
    Any files in sketches/assets/ (the shared asset library) are symlinked in.
    """
    import argparse

    from sketchbook.scaffold import scaffold_sketch

    parser = argparse.ArgumentParser(prog="new-sketch")
    parser.add_argument("name", help="Sketch name / slug (kebab-case, e.g. my-sketch)")
    args = parser.parse_args()

    try:
        sketch_dir = scaffold_sketch(args.name, sketches_dir=_SKETCHES_DIR)
        print(f"Created {sketch_dir.relative_to(_SKETCHES_DIR.parent)}")
    except FileExistsError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc
