"""Acceptance test: Sketch.mode is set correctly by the dev server and bundle builder,
and a sketch can branch on it inside build()."""

from __future__ import annotations

from pathlib import Path

import cv2
import pytest

from sketchbook.core.sketch import Sketch, SketchMode
from sketchbook.core.types import Image
from tests.conftest import make_test_image
from tests.steps import Passthrough


class _ModeCapturingSketch(Sketch):
    """Records self.mode during build() into a class-level list."""

    name = "Mode Capturing"
    description = ""
    date = "2026-04-12"

    captured_modes: list[SketchMode] = []

    def build(self) -> None:
        _ModeCapturingSketch.captured_modes.append(self.mode)
        self.source(
            "photo",
            "assets/photo.png",
            loader=lambda p: Image(cv2.imread(str(p))),
        )


class _BranchingSketch(Sketch):
    """Adds a Passthrough step only in 'build' mode."""

    name = "Branching"
    description = ""
    date = "2026-04-12"

    def build(self) -> None:
        src = self.source(
            "photo",
            "assets/photo.png",
            loader=lambda p: Image(cv2.imread(str(p))),
        )
        if self.mode == "build":
            src.pipe(Passthrough)


@pytest.fixture()
def sketch_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mode_sketch"
    (d / "assets").mkdir(parents=True)
    make_test_image(d / "assets" / "photo.png")
    return d


def test_dev_server_instantiates_sketch_in_dev_mode(sketch_dir: Path) -> None:
    """A sketch loaded by SketchRegistry has mode == 'dev'."""
    from sketchbook.server.registry import SketchRegistry

    registry = SketchRegistry(
        sketches={},
        sketches_dir=sketch_dir.parent,
        candidates={"mode_sketch": _ModeCapturingSketch},
    )
    _ModeCapturingSketch.captured_modes.clear()
    sketch = registry.get_sketch("mode_sketch")
    assert sketch is not None
    assert sketch.mode == "dev"


def test_bundle_builder_instantiates_sketch_in_build_mode(
    sketch_dir: Path, tmp_path: Path
) -> None:
    """A sketch instantiated by the bundle builder has mode == 'build'."""
    from sketchbook.bundle.builder import build_bundle

    class _BundleSketch(Sketch):
        name = "Bundle"
        description = ""
        date = "2026-04-12"

        captured: list[SketchMode] = []

        def build(self) -> None:
            _BundleSketch.captured.append(self.mode)
            src = self.source(
                "photo",
                "assets/photo.png",
                loader=lambda p: Image(cv2.imread(str(p))),
            )
            self.output_bundle(src, "site")

    preset_dir = sketch_dir / "presets"
    preset_dir.mkdir()
    (preset_dir / "default.json").write_text("{}")

    _BundleSketch.captured.clear()
    build_bundle(
        sketch_classes={"mode_sketch": _BundleSketch},
        sketches_dir=sketch_dir.parent,
        output_dir=tmp_path / "dist",
        bundle_name="site",
        workers=1,
    )
    assert all(m == "build" for m in _BundleSketch.captured)
    assert len(_BundleSketch.captured) >= 1


def test_sketch_can_branch_on_mode_in_build(sketch_dir: Path) -> None:
    """A sketch that checks self.mode inside build() produces different DAG structure
    depending on the mode passed at construction."""
    dev_sketch = _BranchingSketch(sketch_dir, mode="dev")
    build_sketch = _BranchingSketch(sketch_dir, mode="build")

    dev_ids = {n.id for n in dev_sketch.dag.topo_sort()}
    build_ids = {n.id for n in build_sketch.dag.topo_sort()}

    assert "passthrough_0" not in dev_ids
    assert "passthrough_0" in build_ids
