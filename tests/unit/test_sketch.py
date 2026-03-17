"""Unit tests for Sketch: source(), .pipe(), DAG wiring, node ID assignment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sketchbook.core.sketch import Sketch, _step_id_base
from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeStep(PipelineStep):
    def setup(self) -> None:
        self.add_input("image", Image)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        return inputs["image"]


class OtherStep(PipelineStep):
    def setup(self) -> None:
        self.add_input("image", Image)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        return inputs["image"]


def _make_asset(sketch_dir: Path) -> None:
    """Write a minimal PNG asset so SourceFile can be pointed at something real."""
    import cv2

    assets = sketch_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(assets / "photo.png"), np.zeros((4, 4, 3), dtype=np.uint8))


class _SingleSourceSketch(Sketch):
    name = "Test"
    description = ""
    date = ""

    def build(self) -> None:
        self.source("photo", "assets/photo.png")


class _PipeSketch(Sketch):
    name = "Test"
    description = ""
    date = ""

    def build(self) -> None:
        src = self.source("photo", "assets/photo.png")
        src.pipe(FakeStep)


class _MultiPipeSketch(Sketch):
    name = "Test"
    description = ""
    date = ""

    def build(self) -> None:
        src = self.source("photo", "assets/photo.png")
        mid = src.pipe(FakeStep)
        mid.pipe(OtherStep)


class _TwoSameStepSketch(Sketch):
    """Uses the same step class twice — IDs should be _0 and _1."""

    name = "Test"
    description = ""
    date = ""

    def build(self) -> None:
        src = self.source("photo", "assets/photo.png")
        first = src.pipe(FakeStep)
        first.pipe(FakeStep)


# ---------------------------------------------------------------------------
# source()
# ---------------------------------------------------------------------------

def test_source_adds_node_to_dag(tmp_path: Path) -> None:
    _make_asset(tmp_path)
    sketch = _SingleSourceSketch(tmp_path)
    assert "source_photo" in sketch.dag.nodes


def test_source_node_id_format(tmp_path: Path) -> None:
    _make_asset(tmp_path)
    sketch = _SingleSourceSketch(tmp_path)
    node = sketch.dag.node("source_photo")
    assert node.id == "source_photo"


# ---------------------------------------------------------------------------
# pipe()
# ---------------------------------------------------------------------------

def test_pipe_adds_node_to_dag(tmp_path: Path) -> None:
    _make_asset(tmp_path)
    sketch = _PipeSketch(tmp_path)
    assert "fake_step_0" in sketch.dag.nodes


def test_pipe_wires_edge(tmp_path: Path) -> None:
    _make_asset(tmp_path)
    sketch = _PipeSketch(tmp_path)
    dst_node = sketch.dag.node("fake_step_0")
    # The "image" input of the piped node should point back to the source
    assert dst_node._inputs["image"].id == "source_photo"


def test_pipe_chain_produces_correct_order(tmp_path: Path) -> None:
    _make_asset(tmp_path)
    sketch = _MultiPipeSketch(tmp_path)
    order = [n.id for n in sketch.dag.topo_sort()]
    assert order.index("source_photo") < order.index("fake_step_0")
    assert order.index("fake_step_0") < order.index("other_step_0")


# ---------------------------------------------------------------------------
# Node ID assignment
# ---------------------------------------------------------------------------

def test_same_step_class_twice_gets_incrementing_ids(tmp_path: Path) -> None:
    _make_asset(tmp_path)
    sketch = _TwoSameStepSketch(tmp_path)
    assert "fake_step_0" in sketch.dag.nodes
    assert "fake_step_1" in sketch.dag.nodes


def test_workdir_path_set_on_piped_node(tmp_path: Path) -> None:
    _make_asset(tmp_path)
    sketch = _PipeSketch(tmp_path)
    node = sketch.dag.node("fake_step_0")
    assert node.workdir_path is not None
    assert "fake_step_0" in node.workdir_path


# ---------------------------------------------------------------------------
# _step_id_base helper
# ---------------------------------------------------------------------------

def test_step_id_base_camel_case() -> None:
    class EdgeDetect(PipelineStep):
        def setup(self): pass
        def process(self, inputs, params): pass

    assert _step_id_base(EdgeDetect) == "edge_detect"


def test_step_id_base_single_word() -> None:
    class Passthrough(PipelineStep):
        def setup(self): pass
        def process(self, inputs, params): pass

    assert _step_id_base(Passthrough) == "passthrough"


def test_step_id_base_acronym() -> None:
    class RGBSplit(PipelineStep):
        def setup(self): pass
        def process(self, inputs, params): pass

    # r_g_b_split is acceptable; just check it's lowercase and snake
    result = _step_id_base(RGBSplit)
    assert result == result.lower()
    assert " " not in result
