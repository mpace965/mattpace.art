"""Scaffolding utilities for creating new sketches."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

log = logging.getLogger("sketchbook.scaffold")

_INIT_TEMPLATE = '''\
"""{slug} — TODO: add description."""

from __future__ import annotations

from sketchbook import Sketch


class {class_name}(Sketch):
    """TODO: add description."""

    name = "{slug}"
    description = ""
    date = "{date}"

    def build(self) -> None:
        """Define the pipeline."""
        pass
'''


def slug_to_class_name(slug: str) -> str:
    """Convert a kebab-case slug to a PascalCase class name.

    Example: "fence-torn-paper" -> "FenceTornPaper"
    """
    return "".join(part.capitalize() for part in slug.split("-"))


def scaffold_sketch(name: str, sketches_dir: str | Path) -> Path:
    """Create a new sketch directory with the standard structure.

    Args:
        name: The sketch slug (kebab-case, e.g. "my-sketch").
        sketches_dir: The directory containing all sketch folders.

    Returns:
        The path to the newly created sketch directory.

    Raises:
        FileExistsError: If a directory with the given name already exists.
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

    class_name = slug_to_class_name(name)
    today = datetime.date.today().isoformat()
    init_content = _INIT_TEMPLATE.format(slug=name, class_name=class_name, date=today)
    (sketch_dir / "__init__.py").write_text(init_content)

    _symlink_shared_assets(sketches_dir, sketch_dir)

    log.info(f"Scaffolded new sketch '{name}' at {sketch_dir}")
    return sketch_dir


def _symlink_shared_assets(sketches_dir: Path, sketch_dir: Path) -> None:
    """Symlink all files from the shared assets library into the sketch's assets dir."""
    shared_assets = sketches_dir / "assets"
    if not shared_assets.is_dir():
        return

    sketch_assets = sketch_dir / "assets"
    for asset in shared_assets.iterdir():
        if asset.is_file():
            link = sketch_assets / asset.name
            link.symlink_to(asset.resolve())
            log.debug(f"Symlinked {asset.name} -> {asset.resolve()}")
