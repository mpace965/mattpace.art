"""Acceptance test: parallel variant building.

Two sketches with two presets each built with workers=2 must produce all four
images and a correct manifest.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest

from sketchbook import Sketch
from sketchbook.bundle.builder import build_bundle
from sketchbook.core.executor import execute
from sketchbook.core.types import Image
from tests.conftest import make_test_image
from tests.steps import EdgeDetect, GaussianBlur


class _SketchA(Sketch):
    name = "Sketch A"
    description = "First parallel test sketch."
    date = "2026-03-31"

    def build(self) -> None:
        """Wire photo through blur then output."""
        photo = self.source("photo", "assets/photo.jpg", loader=lambda p: Image(cv2.imread(str(p))))
        blurred = photo.pipe(GaussianBlur)
        self.output_bundle(blurred, "bundle")


class _SketchB(Sketch):
    name = "Sketch B"
    description = "Second parallel test sketch."
    date = "2026-03-30"

    def build(self) -> None:
        """Wire photo through edge detect then output."""
        photo = self.source("photo", "assets/photo.jpg", loader=lambda p: Image(cv2.imread(str(p))))
        edges = photo.pipe(EdgeDetect)
        self.output_bundle(edges, "bundle")


@pytest.fixture()
def two_sketch_dir(tmp_path: Path) -> Path:
    """Create two sketch directories each with two saved presets."""
    sketches_dir = tmp_path / "sketches"

    for sketch_id, sketch_cls in [("sketch_a", _SketchA), ("sketch_b", _SketchB)]:
        sketch_dir = sketches_dir / sketch_id
        (sketch_dir / "assets").mkdir(parents=True)
        make_test_image(sketch_dir / "assets" / "photo.jpg")

        sketch = sketch_cls(sketch_dir)
        execute(sketch.dag)
        sketch.preset_manager.save_preset("preset_1", sketch.dag)
        sketch.preset_manager.save_preset("preset_2", sketch.dag)

    return sketches_dir


def test_parallel_build_produces_all_images_and_manifest(
    two_sketch_dir: Path, tmp_path: Path
) -> None:
    """workers=2 builds all four variants and writes a correct manifest."""
    output_dir = tmp_path / "output"

    build_bundle(
        {"sketch_a": _SketchA, "sketch_b": _SketchB},
        two_sketch_dir,
        output_dir,
        "bundle",
        workers=2,
    )

    # All four images must exist
    assert (output_dir / "sketch-a" / "preset_1.png").exists()
    assert (output_dir / "sketch-a" / "preset_2.png").exists()
    assert (output_dir / "sketch-b" / "preset_1.png").exists()
    assert (output_dir / "sketch-b" / "preset_2.png").exists()

    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert len(manifest) == 2

    by_slug = {e["slug"]: e for e in manifest}
    assert set(by_slug) == {"sketch-a", "sketch-b"}

    for slug in ("sketch-a", "sketch-b"):
        variants = by_slug[slug]["variants"]
        assert len(variants) == 2
        names = {v["name"] for v in variants}
        assert names == {"preset_1", "preset_2"}

    # Sorted newest-first by date
    assert manifest[0]["slug"] == "sketch-a"
    assert manifest[1]["slug"] == "sketch-b"
