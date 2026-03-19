"""Unit tests for site/builder.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from sketchbook import Sketch
from sketchbook.core.executor import execute
from sketchbook.steps.opencv.blur import GaussianBlur
from sketchbook.steps.opencv.edge_detect import EdgeDetect
from sketchbook.steps.site_output import SiteOutput
from tests.conftest import make_test_image


class _SiteSketch(Sketch):
    name = "Test Sketch"
    description = "Site output test."
    date = "2026-03-18"

    def build(self) -> None:
        photo = self.source("photo", "assets/photo.jpg")
        blurred = photo.pipe(GaussianBlur)
        edges = blurred.pipe(EdgeDetect)
        self.site_output(edges)


@pytest.fixture()
def sketch_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sketches" / "test_sketch"
    (d / "assets").mkdir(parents=True)
    make_test_image(d / "assets" / "photo.jpg")
    return d


def test_site_output_step_is_passthrough(sketch_dir: Path) -> None:
    """SiteOutput step passes the input image through unchanged."""
    from sketchbook.core.types import Image

    import numpy as np

    step = SiteOutput()
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    img = Image(arr)
    result = step.process({"image": img}, {})
    assert result is img


def test_sketch_site_output_adds_site_output_node(sketch_dir: Path) -> None:
    """Sketch.site_output() adds a SiteOutput node to the DAG."""
    sketch = _SiteSketch(sketch_dir)
    site_nodes = [n for n in sketch.dag.topo_sort() if isinstance(n.step, SiteOutput)]
    assert len(site_nodes) == 1


def test_builder_discovers_site_output_nodes(sketch_dir: Path, tmp_path: Path) -> None:
    """build_site skips sketches with no SiteOutput node."""
    from sketchbook import Sketch
    from sketchbook.steps import Passthrough
    from sketchbook.site.builder import build_site

    class _NoSiteSketch(Sketch):
        name = "No Site"
        description = ""
        date = "2026-03-18"

        def build(self) -> None:
            photo = self.source("photo", "assets/photo.jpg")
            photo.pipe(Passthrough)

    no_site_dir = tmp_path / "sketches" / "no_site"
    (no_site_dir / "assets").mkdir(parents=True)
    make_test_image(no_site_dir / "assets" / "photo.jpg")

    dist_dir = tmp_path / "dist"
    build_site({"no_site": _NoSiteSketch}, tmp_path / "sketches", dist_dir)

    # Feed should be empty (no sketch entries)
    feed = (dist_dir / "index.html").read_text()
    assert "no_site" not in feed
    assert "no-site" not in feed


def test_builder_iterates_presets(sketch_dir: Path, tmp_path: Path) -> None:
    """build_site produces a variant image for each saved preset."""
    from sketchbook.site.builder import build_site

    sketch = _SiteSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("preset_a", sketch.dag)
    sketch.preset_manager.save_preset("preset_b", sketch.dag)

    dist_dir = tmp_path / "dist"
    build_site({"test_sketch": _SiteSketch}, sketch_dir.parent, dist_dir)

    assert (dist_dir / "test-sketch" / "variants" / "preset_a.png").exists()
    assert (dist_dir / "test-sketch" / "variants" / "preset_b.png").exists()


def test_builder_renders_feed_with_sketch_link(sketch_dir: Path, tmp_path: Path) -> None:
    """Feed page contains a link to the sketch slug."""
    from sketchbook.site.builder import build_site

    sketch = _SiteSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("only", sketch.dag)

    dist_dir = tmp_path / "dist"
    build_site({"test_sketch": _SiteSketch}, sketch_dir.parent, dist_dir)

    feed = (dist_dir / "index.html").read_text()
    assert "test-sketch" in feed
    assert "Test Sketch" in feed


def test_builder_renders_sketch_page_with_variants(sketch_dir: Path, tmp_path: Path) -> None:
    """Sketch page contains variant image references."""
    from sketchbook.site.builder import build_site

    sketch = _SiteSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("variant_x", sketch.dag)

    dist_dir = tmp_path / "dist"
    build_site({"test_sketch": _SiteSketch}, sketch_dir.parent, dist_dir)

    sketch_page = (dist_dir / "test-sketch" / "index.html").read_text()
    assert "variant_x" in sketch_page


def test_builder_skips_sketch_with_no_presets(sketch_dir: Path, tmp_path: Path) -> None:
    """A sketch with site_output but no saved presets produces no entry in the feed."""
    from sketchbook.site.builder import build_site

    # No presets saved — just build site directly
    dist_dir = tmp_path / "dist"
    build_site({"test_sketch": _SiteSketch}, sketch_dir.parent, dist_dir)

    feed = (dist_dir / "index.html").read_text()
    assert "test-sketch" not in feed


def test_site_presets_filters_to_listed_presets(sketch_dir: Path, tmp_path: Path) -> None:
    """site_presets restricts which presets get baked."""
    from sketchbook.site.builder import build_site

    class _FilteredSketch(_SiteSketch):
        site_presets = ["preset_a"]

    sketch = _FilteredSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("preset_a", sketch.dag)
    sketch.preset_manager.save_preset("preset_b", sketch.dag)

    dist_dir = tmp_path / "dist"
    build_site({"test_sketch": _FilteredSketch}, sketch_dir.parent, dist_dir)

    assert (dist_dir / "test-sketch" / "variants" / "preset_a.png").exists()
    assert not (dist_dir / "test-sketch" / "variants" / "preset_b.png").exists()


def test_site_presets_unknown_name_does_not_crash(sketch_dir: Path, tmp_path: Path) -> None:
    """site_presets referencing a non-existent preset logs a warning but doesn't crash."""
    from sketchbook.site.builder import build_site

    class _BadPresetSketch(_SiteSketch):
        site_presets = ["real_preset", "does_not_exist"]

    sketch = _BadPresetSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("real_preset", sketch.dag)

    dist_dir = tmp_path / "dist"
    build_site({"test_sketch": _BadPresetSketch}, sketch_dir.parent, dist_dir)

    assert (dist_dir / "test-sketch" / "variants" / "real_preset.png").exists()
    assert not (dist_dir / "test-sketch" / "variants" / "does_not_exist.png").exists()


def test_sketch_page_hides_name_for_single_variant(sketch_dir: Path, tmp_path: Path) -> None:
    """Sketch page omits the variant name label when there is only one variant."""
    from sketchbook.site.builder import build_site

    sketch = _SiteSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("only_one", sketch.dag)

    dist_dir = tmp_path / "dist"
    build_site({"test_sketch": _SiteSketch}, sketch_dir.parent, dist_dir)

    sketch_page = (dist_dir / "test-sketch" / "index.html").read_text()
    # The anchor id should still be present, but the visible label should not appear
    assert 'id="only_one"' in sketch_page
    assert 'href="#only_one"' not in sketch_page


def test_sketch_page_shows_name_for_multiple_variants(sketch_dir: Path, tmp_path: Path) -> None:
    """Sketch page shows linkable variant names when there are multiple variants."""
    from sketchbook.site.builder import build_site

    sketch = _SiteSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("alpha", sketch.dag)
    sketch.preset_manager.save_preset("beta", sketch.dag)

    dist_dir = tmp_path / "dist"
    build_site({"test_sketch": _SiteSketch}, sketch_dir.parent, dist_dir)

    sketch_page = (dist_dir / "test-sketch" / "index.html").read_text()
    assert 'href="#alpha"' in sketch_page
    assert 'href="#beta"' in sketch_page
