"""Increment 7 acceptance tests: output bundle generation."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest

from sketchbook import Sketch
from sketchbook.core.executor import execute
from sketchbook.core.types import Image
from tests.conftest import make_test_image
from tests.steps import EdgeDetect, GaussianBlur, Passthrough


class _EdgePortraitSketch(Sketch):
    """Sketch with output_bundle node and named presets."""

    name = "Edge Portrait"
    description = "Canny edge detection on a portrait."
    date = "2026-03-18"

    def build(self) -> None:
        """Wire photo through blur, edge detect, then mark as bundle output."""
        photo = self.source("photo", "assets/photo.jpg", loader=lambda p: Image(cv2.imread(str(p))))
        blurred = photo.pipe(GaussianBlur)
        edges = blurred.pipe(EdgeDetect)
        self.output_bundle(edges, "bundle")


@pytest.fixture()
def tmp_sketch_with_presets(tmp_path: Path) -> Path:
    """Create a sketch directory with two saved presets."""
    sketch_dir = tmp_path / "sketches" / "edge_portrait"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "photo.jpg")

    sketch = _EdgePortraitSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("heavy_edges", sketch.dag)

    # Change a param and save a second preset
    edge_node = sketch.dag.node("edge_detect_0")
    edge_node.step._param_registry.load_values({"threshold1": 200.0})
    sketch.preset_manager.save_preset("soft_edges", sketch.dag)

    return tmp_path


def test_build_produces_bundle_with_variants(tmp_sketch_with_presets: Path) -> None:
    """build_bundle generates a JSON blob and baked images for each preset."""
    from sketchbook.bundle.builder import build_bundle

    sketches_dir = tmp_sketch_with_presets / "sketches"
    output_dir = tmp_sketch_with_presets / "output"

    build_bundle({"edge_portrait": _EdgePortraitSketch}, sketches_dir, output_dir, "bundle")

    bundle_path = output_dir / "manifest.json"
    assert bundle_path.exists()

    assert (output_dir / "edge-portrait" / "heavy_edges.png").exists()
    assert (output_dir / "edge-portrait" / "soft_edges.png").exists()

    bundle = json.loads(bundle_path.read_text())
    assert len(bundle) == 1
    entry = bundle[0]
    assert entry["slug"] == "edge-portrait"
    assert entry["name"] == "Edge Portrait"

    variant_names = [v["name"] for v in entry["variants"]]
    assert "heavy_edges" in variant_names
    assert "soft_edges" in variant_names

    img_bytes = (output_dir / "edge-portrait" / "heavy_edges.png").read_bytes()
    assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_build_without_output_bundle_produces_empty_bundle(tmp_path: Path) -> None:
    """A sketch with no output_bundle node doesn't appear in the bundle JSON."""
    from sketchbook.bundle.builder import build_bundle

    class _NoBundleSketch(Sketch):
        name = "Hello"
        description = "No output bundle."
        date = "2026-03-18"

        def build(self) -> None:
            photo = self.source("photo", "assets/photo.jpg")
            photo.pipe(Passthrough)

    sketch_dir = tmp_path / "sketches" / "hello"
    (sketch_dir / "assets").mkdir(parents=True)
    make_test_image(sketch_dir / "assets" / "photo.jpg")

    output_dir = tmp_path / "output"
    build_bundle({"hello": _NoBundleSketch}, tmp_path / "sketches", output_dir, "bundle")

    bundle = json.loads((output_dir / "manifest.json").read_text())
    assert bundle == []
