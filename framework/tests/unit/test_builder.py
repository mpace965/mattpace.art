"""Unit tests for site/builder.py."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest

from sketchbook import Sketch
from sketchbook.core.executor import execute
from sketchbook.core.types import Image
from sketchbook.steps.output_bundle import OutputBundle
from tests.conftest import make_test_image
from tests.steps import EdgeDetect, GaussianBlur, Passthrough


class _SiteSketch(Sketch):
    name = "Test Sketch"
    description = "Output bundle test."
    date = "2026-03-18"

    def build(self) -> None:
        photo = self.source("photo", "assets/photo.jpg", loader=lambda p: Image(cv2.imread(str(p))))
        blurred = photo.pipe(GaussianBlur)
        edges = blurred.pipe(EdgeDetect)
        self.output_bundle(edges, "bundle")


@pytest.fixture()
def sketch_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sketches" / "test_sketch"
    (d / "assets").mkdir(parents=True)
    make_test_image(d / "assets" / "photo.jpg")
    return d


def test_output_bundle_step_is_passthrough(sketch_dir: Path) -> None:
    """OutputBundle step passes the input image through unchanged."""
    import numpy as np

    from sketchbook.core.types import Image

    step = OutputBundle("bundle")
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    img = Image(arr)
    result = step.process({"image": img}, {})
    assert result is img


def test_output_bundle_dsl_adds_node(sketch_dir: Path) -> None:
    """Sketch.output_bundle() adds an OutputBundle node to the DAG with the given name."""
    sketch = _SiteSketch(sketch_dir)
    bundle_nodes = [n for n in sketch.dag.topo_sort() if isinstance(n.step, OutputBundle)]
    assert len(bundle_nodes) == 1
    assert bundle_nodes[0].step.bundle_name == "bundle"


def test_site_output_bundle_is_no_arg_output_bundle(sketch_dir: Path) -> None:
    """SiteOutputBundle is an OutputBundle with bundle_name='static_site' and no args."""
    from sketchbook.steps.output_bundle import OutputBundle

    class _FakeSiteOutputBundle(OutputBundle):
        def __init__(self) -> None:
            super().__init__("bundle")

    class _PipeSketch(Sketch):
        name = "Pipe"
        description = ""
        date = "2026-03-18"

        def build(self) -> None:
            photo = self.source("photo", "assets/photo.jpg")
            photo.pipe(_FakeSiteOutputBundle)

    sketch = _PipeSketch(sketch_dir)
    bundle_nodes = [n for n in sketch.dag.topo_sort() if isinstance(n.step, OutputBundle)]
    assert len(bundle_nodes) == 1
    assert bundle_nodes[0].step.bundle_name == "bundle"


def test_sketch_output_bundle_uses_given_name(sketch_dir: Path) -> None:
    """Sketch.output_bundle() attaches the given bundle_name to the node."""

    class _CustomBundleSketch(Sketch):
        name = "Custom"
        description = ""
        date = "2026-03-18"

        def build(self) -> None:
            photo = self.source("photo", "assets/photo.jpg")
            edges = photo.pipe(GaussianBlur)
            self.output_bundle(edges, "my_bundle")

    sketch = _CustomBundleSketch(sketch_dir)
    bundle_nodes = [n for n in sketch.dag.topo_sort() if isinstance(n.step, OutputBundle)]
    assert len(bundle_nodes) == 1
    assert bundle_nodes[0].step.bundle_name == "my_bundle"


def test_builder_discovers_output_bundle_nodes(sketch_dir: Path, tmp_path: Path) -> None:
    """build_bundle skips sketches with no OutputBundle node for the given bundle name."""
    from sketchbook.site.builder import build_bundle

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

    output_dir = tmp_path / "output"
    build_bundle({"no_site": _NoSiteSketch}, tmp_path / "sketches", output_dir, "bundle")

    bundle = json.loads((output_dir / "manifest.json").read_text())
    assert bundle == []


def test_builder_ignores_different_bundle_name(sketch_dir: Path, tmp_path: Path) -> None:
    """build_bundle skips OutputBundle nodes whose name doesn't match the requested bundle."""
    from sketchbook.site.builder import build_bundle

    class _OtherBundleSketch(Sketch):
        name = "Other"
        description = ""
        date = "2026-03-18"

        def build(self) -> None:
            photo = self.source("photo", "assets/photo.jpg")
            edges = photo.pipe(GaussianBlur)
            self.output_bundle(edges, "other_bundle")

    other_dir = tmp_path / "sketches" / "other"
    (other_dir / "assets").mkdir(parents=True)
    make_test_image(other_dir / "assets" / "photo.jpg")

    output_dir = tmp_path / "output"
    build_bundle({"other": _OtherBundleSketch}, tmp_path / "sketches", output_dir, "bundle")

    bundle = json.loads((output_dir / "manifest.json").read_text())
    assert bundle == []


def test_builder_iterates_presets(sketch_dir: Path, tmp_path: Path) -> None:
    """build_bundle produces a variant image for each saved preset."""
    from sketchbook.site.builder import build_bundle

    sketch = _SiteSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("preset_a", sketch.dag)
    sketch.preset_manager.save_preset("preset_b", sketch.dag)

    output_dir = tmp_path / "output"
    build_bundle({"test_sketch": _SiteSketch}, sketch_dir.parent, output_dir, "bundle")

    assert (output_dir / "test-sketch" / "preset_a.png").exists()
    assert (output_dir / "test-sketch" / "preset_b.png").exists()


def test_builder_writes_json_bundle(sketch_dir: Path, tmp_path: Path) -> None:
    """build_bundle writes a JSON file with sketch metadata and variant entries."""
    from sketchbook.site.builder import build_bundle

    sketch = _SiteSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("only", sketch.dag)

    output_dir = tmp_path / "output"
    build_bundle({"test_sketch": _SiteSketch}, sketch_dir.parent, output_dir, "bundle")

    bundle = json.loads((output_dir / "manifest.json").read_text())
    assert len(bundle) == 1
    entry = bundle[0]
    assert entry["slug"] == "test-sketch"
    assert entry["name"] == "Test Sketch"
    assert entry["description"] == "Output bundle test."
    assert entry["date"] == "2026-03-18"
    assert len(entry["variants"]) == 1
    assert entry["variants"][0]["name"] == "only"
    assert entry["variants"][0]["image_path"] == "test-sketch/only.png"


def test_builder_skips_sketch_with_no_presets(sketch_dir: Path, tmp_path: Path) -> None:
    """A sketch with output_bundle but no saved presets produces no entry in the bundle."""
    from sketchbook.site.builder import build_bundle

    output_dir = tmp_path / "output"
    build_bundle({"test_sketch": _SiteSketch}, sketch_dir.parent, output_dir, "bundle")

    bundle = json.loads((output_dir / "manifest.json").read_text())
    assert bundle == []


def test_output_bundle_stores_presets_kwarg(sketch_dir: Path) -> None:
    """OutputBundle stores the presets list when provided."""
    node = OutputBundle("bundle", presets=["a", "b"])
    assert node.presets == ["a", "b"]


def test_output_bundle_default_presets_is_none(sketch_dir: Path) -> None:
    """OutputBundle.presets defaults to None (meaning all saved presets)."""
    node = OutputBundle("bundle")
    assert node.presets is None


def test_builder_uses_node_presets_to_filter(sketch_dir: Path, tmp_path: Path) -> None:
    """OutputBundle.presets restricts which presets get baked."""
    from sketchbook.site.builder import build_bundle

    class _FilteredBundleSketch(Sketch):
        name = "Filtered"
        description = ""
        date = "2026-03-18"

        def build(self) -> None:
            photo = self.source(
                "photo", "assets/photo.jpg", loader=lambda p: Image(cv2.imread(str(p)))
            )
            blurred = photo.pipe(GaussianBlur)
            edges = blurred.pipe(EdgeDetect)
            self.output_bundle(edges, "bundle", presets=["preset_a"])

    sketch = _FilteredBundleSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("preset_a", sketch.dag)
    sketch.preset_manager.save_preset("preset_b", sketch.dag)

    output_dir = tmp_path / "output"
    build_bundle({"test_sketch": _FilteredBundleSketch}, sketch_dir.parent, output_dir, "bundle")

    assert (output_dir / "test-sketch" / "preset_a.png").exists()
    assert not (output_dir / "test-sketch" / "preset_b.png").exists()


def test_builder_node_presets_unknown_name_does_not_crash(sketch_dir: Path, tmp_path: Path) -> None:
    """OutputBundle.presets referencing a non-existent preset logs a warning but doesn't crash."""
    from sketchbook.site.builder import build_bundle

    class _BadNodePresetSketch(Sketch):
        name = "Bad"
        description = ""
        date = "2026-03-18"

        def build(self) -> None:
            photo = self.source(
                "photo", "assets/photo.jpg", loader=lambda p: Image(cv2.imread(str(p)))
            )
            blurred = photo.pipe(GaussianBlur)
            edges = blurred.pipe(EdgeDetect)
            self.output_bundle(edges, "bundle", presets=["real_preset", "does_not_exist"])

    sketch = _BadNodePresetSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("real_preset", sketch.dag)

    output_dir = tmp_path / "output"
    build_bundle({"test_sketch": _BadNodePresetSketch}, sketch_dir.parent, output_dir, "bundle")

    assert (output_dir / "test-sketch" / "real_preset.png").exists()
    assert not (output_dir / "test-sketch" / "does_not_exist.png").exists()


def test_builder_warns_on_duplicate_bundle_nodes(
    sketch_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A sketch with two OutputBundle nodes for the same bundle name emits a warning."""
    import logging

    from sketchbook.site.builder import build_bundle

    class _DuplicateOutputSketch(Sketch):
        name = "Duplicate"
        description = ""
        date = "2026-03-18"

        def build(self) -> None:
            photo = self.source("photo", "assets/photo.jpg")
            blurred = photo.pipe(GaussianBlur)
            self.output_bundle(blurred, "bundle")
            edges = blurred.pipe(EdgeDetect)
            self.output_bundle(edges, "bundle")

    sketch = _DuplicateOutputSketch(sketch_dir)
    execute(sketch.dag)
    sketch.preset_manager.save_preset("p", sketch.dag)

    output_dir = tmp_path / "output"
    with caplog.at_level(logging.WARNING, logger="sketchbook.site.builder"):
        build_bundle(
            {"test_sketch": _DuplicateOutputSketch},
            sketch_dir.parent,
            output_dir,
            "bundle",
        )

    assert any("multiple OutputBundle" in r.message for r in caplog.records)
