"""Increment 7 acceptance tests: static site generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from sketchbook import Sketch
from sketchbook.core.executor import execute
from sketchbook.steps import Passthrough
from sketchbook.steps.opencv.blur import GaussianBlur
from sketchbook.steps.opencv.edge_detect import EdgeDetect
from tests.conftest import make_test_image


class _EdgePortraitSketch(Sketch):
    """Sketch with site_output node and named presets."""

    name = "Edge Portrait"
    description = "Canny edge detection on a portrait."
    date = "2026-03-18"

    def build(self) -> None:
        """Wire photo through blur, edge detect, then mark as site output."""
        photo = self.source("photo", "assets/photo.jpg")
        blurred = photo.pipe(GaussianBlur)
        edges = blurred.pipe(EdgeDetect)
        self.site_output(edges)


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


def test_build_produces_site_with_variants(tmp_sketch_with_presets: Path) -> None:
    """build_site generates feed and sketch pages with variant images for each preset."""
    from sketchbook.site.builder import build_site

    sketches_dir = tmp_sketch_with_presets / "sketches"
    dist_dir = tmp_sketch_with_presets / "dist"

    build_site({"edge_portrait": _EdgePortraitSketch}, sketches_dir, dist_dir)

    assert (dist_dir / "index.html").exists()
    assert (dist_dir / "edge-portrait" / "index.html").exists()
    assert (dist_dir / "edge-portrait" / "variants" / "heavy_edges.png").exists()
    assert (dist_dir / "edge-portrait" / "variants" / "soft_edges.png").exists()

    feed_html = (dist_dir / "index.html").read_text()
    assert "edge-portrait" in feed_html

    img_bytes = (dist_dir / "edge-portrait" / "variants" / "heavy_edges.png").read_bytes()
    assert len(img_bytes) > 100


def test_build_without_site_output_produces_empty_feed(tmp_path: Path) -> None:
    """A sketch with no site_output node doesn't appear in the build."""
    from sketchbook.site.builder import build_site

    class _NoSiteSketch(Sketch):
        name = "Hello"
        description = "No site output."
        date = "2026-03-18"

        def build(self) -> None:
            photo = self.source("photo", "assets/photo.jpg")
            photo.pipe(Passthrough)

    sketch_dir = tmp_path / "sketches" / "hello"
    (sketch_dir / "assets").mkdir(parents=True)
    make_test_image(sketch_dir / "assets" / "photo.jpg")

    dist_dir = tmp_path / "dist"
    build_site({"hello": _NoSiteSketch}, tmp_path / "sketches", dist_dir)

    feed_html = (dist_dir / "index.html").read_text()
    assert "hello" not in feed_html
