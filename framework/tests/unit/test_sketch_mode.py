"""Unit tests for Sketch.mode: type, constructor parameter, read-only enforcement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sketchbook.core.sketch import Sketch, SketchMode
from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image


class _MinimalStep(PipelineStep):
    def setup(self) -> None:
        self.add_input("image", Image)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        return inputs["image"]


class _ModeCheckSketch(Sketch):
    """Sketch that records self.mode during build()."""

    name = "Mode Check"
    description = ""
    date = "2026-04-12"

    mode_seen_in_build: SketchMode | None = None

    def build(self) -> None:
        _ModeCheckSketch.mode_seen_in_build = self.mode


class _ConditionalSketch(Sketch):
    """Adds a step only in 'build' mode."""

    name = "Conditional"
    description = ""
    date = "2026-04-12"

    def build(self) -> None:
        if self.mode == "build":
            self.source("photo", "assets/photo.png")


def test_sketch_default_mode_is_dev(tmp_path: Path) -> None:
    """Sketch() with no mode argument defaults to 'dev'."""
    sketch = _ModeCheckSketch(tmp_path)
    assert sketch.mode == "dev"


def test_sketch_mode_dev_stored(tmp_path: Path) -> None:
    """Sketch(mode='dev') stores 'dev' on self.mode."""
    sketch = _ModeCheckSketch(tmp_path, mode="dev")
    assert sketch.mode == "dev"


def test_sketch_mode_build_stored(tmp_path: Path) -> None:
    """Sketch(mode='build') stores 'build' on self.mode."""
    sketch = _ModeCheckSketch(tmp_path, mode="build")
    assert sketch.mode == "build"


def test_sketch_mode_is_readonly(tmp_path: Path) -> None:
    """Assigning to sketch.mode after construction raises AttributeError."""
    sketch = _ModeCheckSketch(tmp_path)
    with pytest.raises(AttributeError):
        sketch.mode = "build"  # type: ignore[misc]


def test_sketch_invalid_mode_raises(tmp_path: Path) -> None:
    """Passing an unrecognised mode string raises ValueError with a helpful message."""
    with pytest.raises(ValueError, match="mode"):
        _ModeCheckSketch(tmp_path, mode="invalid")  # type: ignore[arg-type]


def test_mode_is_set_before_build_is_called(tmp_path: Path) -> None:
    """self.mode is accessible inside build() — set before build() is called."""
    _ModeCheckSketch.mode_seen_in_build = None
    _ModeCheckSketch(tmp_path, mode="build")
    assert _ModeCheckSketch.mode_seen_in_build == "build"


def test_mode_dev_produces_expected_dag_structure(tmp_path: Path) -> None:
    """A sketch that conditionally adds a node in 'build' mode does not add it in 'dev'."""
    sketch = _ConditionalSketch(tmp_path, mode="dev")
    assert len(sketch.dag.nodes) == 0


def test_mode_build_produces_expected_dag_structure(tmp_path: Path) -> None:
    """The same sketch instantiated with mode='build' includes the conditional node."""
    (tmp_path / "assets").mkdir()
    sketch = _ConditionalSketch(tmp_path, mode="build")
    assert "source_photo" in sketch.dag.nodes


# ---------------------------------------------------------------------------
# Dev server registry passes mode="dev"
# ---------------------------------------------------------------------------

def test_registry_loads_sketch_in_dev_mode(tmp_path: Path) -> None:
    """Sketch instances loaded via SketchRegistry have mode == 'dev'."""
    from sketchbook.server.registry import SketchRegistry

    sketch_dir = tmp_path / "mode_check"
    sketch_dir.mkdir()

    _ModeCheckSketch.mode_seen_in_build = None
    registry = SketchRegistry(
        sketches={},
        sketches_dir=tmp_path,
        candidates={"mode_check": _ModeCheckSketch},
    )
    sketch = registry.get_sketch("mode_check")
    assert sketch is not None
    assert sketch.mode == "dev"


# ---------------------------------------------------------------------------
# Bundle builder passes mode="build"
# ---------------------------------------------------------------------------

def test_build_variant_uses_build_mode(tmp_path: Path) -> None:
    """_build_variant instantiates the sketch with mode='build'."""
    from sketchbook.bundle.builder import _build_variant, _VariantTask

    class _RecordingSketch(Sketch):
        name = "Recording"
        description = ""
        date = "2026-04-12"

        captured: list[SketchMode] = []

        def build(self) -> None:
            _RecordingSketch.captured.append(self.mode)

    sketch_dir = tmp_path / "recording"
    sketch_dir.mkdir()

    _RecordingSketch.captured.clear()
    task = _VariantTask(
        sketch_id="recording",
        sketch_cls=_RecordingSketch,
        sketch_dir=sketch_dir,
        preset_name="default",
        sketch_output_dir=tmp_path / "out",
        bundle_name="site",
    )
    # _build_variant will fail at execute() since there's no real DAG,
    # but the mode should already be captured during build()
    try:
        _build_variant(task)
    except Exception:
        pass
    assert _RecordingSketch.captured == ["build"]


def test_discover_sketch_uses_build_mode(tmp_path: Path) -> None:
    """_discover_sketch instantiates the sketch with mode='build'."""
    from sketchbook.bundle.builder import _discover_sketch

    class _DiscoverySketch(Sketch):
        name = "Discovery"
        description = ""
        date = "2026-04-12"

        captured: list[SketchMode] = []

        def build(self) -> None:
            _DiscoverySketch.captured.append(self.mode)
            src = self.source("photo", "assets/photo.png")
            self.output_bundle(src, "site")

    sketch_dir = tmp_path / "discovery"
    (sketch_dir / "assets").mkdir(parents=True)
    preset_dir = sketch_dir / "presets"
    preset_dir.mkdir()
    (preset_dir / "default.json").write_text("{}")

    _DiscoverySketch.captured.clear()
    _discover_sketch(
        sketch_id="discovery",
        sketch_cls=_DiscoverySketch,
        sketches_dir=tmp_path,
        output_dir=tmp_path / "dist",
        bundle_name="site",
    )
    assert _DiscoverySketch.captured == ["build"]
