"""Scaffolding utilities for creating new sketches."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

log = logging.getLogger("sketchbook.scaffold")

_INIT_TEMPLATE = '''\
"""{slug} — TODO: add description."""

from __future__ import annotations

from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import sketch, step


@sketch(date="{date}")
def {fn_name}() -> None:
    """TODO: add description."""
    pass
'''


def slug_to_class_name(slug: str) -> str:
    """Convert a kebab-case slug to a PascalCase class name.

    Example: "fence-torn-paper" -> "FenceTornPaper"
    """
    return "".join(part.capitalize() for part in slug.split("-"))


def scaffold_sketch(
    name: str,
    sketches_dir: str | Path,
    assets: list[str] | None = None,
) -> Path:
    """Create a new sketch directory with the standard structure.

    Args:
        name: The sketch slug (kebab-case, e.g. "my-sketch").
        sketches_dir: The directory containing all sketch folders.
        assets: Filenames to symlink from the shared sketches/assets/ library.
                Defaults to none. Pass an explicit list to opt in.

    Returns:
        The path to the newly created sketch directory.

    Raises:
        FileExistsError: If a directory with the given name already exists.
        FileNotFoundError: If a requested asset is not in the shared library.
    """
    sketches_dir = Path(sketches_dir)
    sketch_dir = sketches_dir / name

    if sketch_dir.exists():
        raise FileExistsError(f"Sketch '{name}' already exists at {sketch_dir}")

    sketch_dir.mkdir(parents=True)
    (sketch_dir / "assets").mkdir()
    presets_dir = sketch_dir / "presets"
    presets_dir.mkdir()
    (presets_dir / "_active.json").write_text("{}\n")

    fn_name = name.replace("-", "_")
    today = datetime.date.today().isoformat()
    init_content = _INIT_TEMPLATE.format(slug=name, fn_name=fn_name, date=today)
    (sketch_dir / "__init__.py").write_text(init_content)

    if assets:
        _symlink_assets(sketches_dir, sketch_dir, assets)

    log.info(f"Scaffolded new sketch '{name}' at {sketch_dir}")
    return sketch_dir


def _symlink_assets(sketches_dir: Path, sketch_dir: Path, filenames: list[str]) -> None:
    """Symlink the named files from the shared asset library into the sketch's assets dir."""
    shared_assets = sketches_dir / "assets"
    sketch_assets = sketch_dir / "assets"
    for filename in filenames:
        source = shared_assets / filename
        if not source.exists():
            raise FileNotFoundError(
                f"Asset '{filename}' not found in shared library at {shared_assets}"
            )
        (sketch_assets / filename).symlink_to(source.resolve())
        log.debug(f"Symlinked {filename} -> {source.resolve()}")
