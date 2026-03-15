"""Shared utilities for resolving sketch paths.

This is the single module that knows the repo layout. All pipeline and
playground code imports from here — never hardcode repo-relative paths elsewhere.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKETCHES_DIR = REPO_ROOT / "site" / "sketches"

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def sketch_assets_dir(sketch_name: str) -> Path:
    """Return the assets/ path for a named sketch. Does not assert existence."""
    return SKETCHES_DIR / sketch_name / "assets"


def list_sketches() -> list[str]:
    """Return names of all sketch directories (excludes _-prefixed dirs)."""
    if not SKETCHES_DIR.exists():
        return []
    return sorted(
        d.name
        for d in SKETCHES_DIR.iterdir()
        if d.is_dir() and not d.name.startswith("_")
    )


def sketch_image_paths(sketch_name: str, suffixes: tuple[str, ...] = IMAGE_SUFFIXES) -> list[Path]:
    """Return all image files in a sketch's assets/ directory."""
    assets = sketch_assets_dir(sketch_name)
    if not assets.exists():
        return []
    return [p for p in sorted(assets.iterdir()) if p.suffix.lower() in suffixes]


def find_image(sketch_name: str, stem: str) -> Path | None:
    """Find a single image in a sketch's assets/ by stem (no extension needed)."""
    assets = sketch_assets_dir(sketch_name)
    for suffix in IMAGE_SUFFIXES:
        candidate = assets / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None
