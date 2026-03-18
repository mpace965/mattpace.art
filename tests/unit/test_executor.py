"""Unit tests for the pipeline executor: full execution, failure propagation, workdir write, stale file deletion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sketchbook.core.dag import DAG, DAGNode
from sketchbook.core.executor import execute, execute_partial
from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _ConstantStep(PipelineStep):
    """Always returns a fixed Image regardless of inputs."""

    def __init__(self, image: Image) -> None:
        self._image = image
        super().__init__()

    def setup(self) -> None:
        pass

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        return self._image


class _PassthroughStep(PipelineStep):
    def setup(self) -> None:
        self.add_input("image", Image)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        return inputs["image"]


class _ParamCapturingStep(PipelineStep):
    """Records the params dict it receives in process()."""

    def __init__(self) -> None:
        self.received_params: dict[str, Any] = {}
        super().__init__()

    def setup(self) -> None:
        self.add_input("image", Image)
        self.add_param("strength", float, default=42.0)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        self.received_params = dict(params)
        return inputs["image"]


class _BrokenStep(PipelineStep):
    def setup(self) -> None:
        self.add_input("image", Image)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        raise RuntimeError("intentional failure")


def _small_image() -> Image:
    return Image(np.zeros((4, 4, 3), dtype=np.uint8))


def _make_node(node_id: str, step: PipelineStep, workdir: Path | None = None) -> DAGNode:
    wp = str(workdir / f"{node_id}.png") if workdir else None
    return DAGNode(step, node_id, workdir_path=wp)


# ---------------------------------------------------------------------------
# Full execution
# ---------------------------------------------------------------------------

def test_execute_single_source_node() -> None:
    img = _small_image()
    dag = DAG()
    dag.add_node(_make_node("src", _ConstantStep(img)))

    result = execute(dag)

    assert result.ok
    assert dag.node("src").output is img


def test_execute_source_to_passthrough() -> None:
    img = _small_image()
    dag = DAG()
    dag.add_node(_make_node("src", _ConstantStep(img)))
    dag.add_node(_make_node("pass", _PassthroughStep()))
    dag.connect("src", "pass", "image")

    result = execute(dag)

    assert result.ok
    assert dag.node("pass").output is img


# ---------------------------------------------------------------------------
# Workdir write
# ---------------------------------------------------------------------------

def test_execute_writes_workdir_file(tmp_path: Path) -> None:
    img = _small_image()
    dag = DAG()
    dag.add_node(_make_node("src", _ConstantStep(img)))
    pt_node = _make_node("pass", _PassthroughStep(), workdir=tmp_path)
    dag.add_node(pt_node)
    dag.connect("src", "pass", "image")

    execute(dag)

    assert (tmp_path / "pass.png").exists()


# ---------------------------------------------------------------------------
# Params
# ---------------------------------------------------------------------------

def test_executor_passes_params_to_process() -> None:
    img = _small_image()
    step = _ParamCapturingStep()
    step._param_registry.set_value("strength", 99.0)

    dag = DAG()
    dag.add_node(_make_node("src", _ConstantStep(img)))
    dag.add_node(_make_node("capture", step))
    dag.connect("src", "capture", "image")

    execute(dag)

    assert step.received_params["strength"] == 99.0


def test_executor_uses_registry_not_empty_dict() -> None:
    img = _small_image()
    step = _ParamCapturingStep()

    dag = DAG()
    dag.add_node(_make_node("src", _ConstantStep(img)))
    dag.add_node(_make_node("capture", step))
    dag.connect("src", "capture", "image")

    execute(dag)

    assert "strength" in step.received_params


# ---------------------------------------------------------------------------
# Failure propagation
# ---------------------------------------------------------------------------

def test_failed_node_propagates_to_downstream() -> None:
    img = _small_image()
    dag = DAG()
    dag.add_node(_make_node("src", _ConstantStep(img)))
    dag.add_node(_make_node("broken", _BrokenStep()))
    dag.add_node(_make_node("downstream", _PassthroughStep()))
    dag.connect("src", "broken", "image")
    dag.connect("broken", "downstream", "image")

    result = execute(dag)

    assert "broken" in result.errors
    assert "downstream" in result.errors
    assert dag.node("downstream").output is None


def test_failed_node_clears_output() -> None:
    img = _small_image()
    dag = DAG()
    dag.add_node(_make_node("src", _ConstantStep(img)))
    dag.add_node(_make_node("broken", _BrokenStep()))
    dag.connect("src", "broken", "image")

    result = execute(dag)

    assert not result.ok
    assert dag.node("broken").output is None


# ---------------------------------------------------------------------------
# Stale file deletion
# ---------------------------------------------------------------------------

def test_execute_result_records_executed_nodes() -> None:
    img = _small_image()
    dag = DAG()
    dag.add_node(_make_node("src", _ConstantStep(img)))
    dag.add_node(_make_node("pass", _PassthroughStep()))
    dag.connect("src", "pass", "image")

    result = execute(dag)

    assert "src" in result.executed
    assert "pass" in result.executed


# ---------------------------------------------------------------------------
# Partial execution
# ---------------------------------------------------------------------------

def test_execute_partial_skips_non_descendants() -> None:
    """execute_partial on source_b only runs source_b and its descendants, not source_a."""
    img = _small_image()
    dag = DAG()
    dag.add_node(_make_node("src_a", _ConstantStep(img)))
    dag.add_node(_make_node("src_b", _ConstantStep(img)))
    dst_a = _make_node("dst_a", _PassthroughStep())
    dst_b = _make_node("dst_b", _PassthroughStep())
    dag.add_node(dst_a)
    dag.add_node(dst_b)
    dag.connect("src_a", "dst_a", "image")
    dag.connect("src_b", "dst_b", "image")

    # Run full first to populate all outputs
    execute(dag)

    # Now partial-run only src_b branch
    result = execute_partial(dag, ["src_b"])

    assert "src_b" in result.executed
    assert "dst_b" in result.executed
    assert "src_a" not in result.executed
    assert "dst_a" not in result.executed


def test_execute_partial_includes_start_node() -> None:
    img = _small_image()
    dag = DAG()
    dag.add_node(_make_node("src", _ConstantStep(img)))
    dag.add_node(_make_node("pass", _PassthroughStep()))
    dag.connect("src", "pass", "image")

    execute(dag)
    result = execute_partial(dag, ["src"])

    assert "src" in result.executed
    assert "pass" in result.executed


# ---------------------------------------------------------------------------
# Optional input handling
# ---------------------------------------------------------------------------

class _OptionalMaskStep(PipelineStep):
    """Step that records whether mask was received."""

    def __init__(self) -> None:
        self.received_mask = object()  # sentinel
        super().__init__()

    def setup(self) -> None:
        self.add_input("image", Image)
        self.add_input("mask", Image, optional=True)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        self.received_mask = inputs.get("mask")
        return inputs["image"]


def test_optional_input_receives_none_when_not_connected() -> None:
    img = _small_image()
    step = _OptionalMaskStep()
    dag = DAG()
    dag.add_node(_make_node("src", _ConstantStep(img)))
    dag.add_node(_make_node("opt", step))
    dag.connect("src", "opt", "image")

    execute(dag)

    assert step.received_mask is None


def test_optional_input_receives_image_when_connected() -> None:
    img = _small_image()
    mask_img = _small_image()
    step = _OptionalMaskStep()
    dag = DAG()
    dag.add_node(_make_node("src", _ConstantStep(img)))
    dag.add_node(_make_node("mask_src", _ConstantStep(mask_img)))
    dag.add_node(_make_node("opt", step))
    dag.connect("src", "opt", "image")
    dag.connect("mask_src", "opt", "mask")

    execute(dag)

    assert step.received_mask is mask_img


# ---------------------------------------------------------------------------
# Stale file deletion
# ---------------------------------------------------------------------------

def test_failed_node_deletes_stale_workdir_file(tmp_path: Path) -> None:
    img = _small_image()
    stale = tmp_path / "broken.png"
    stale.write_bytes(b"old")

    dag = DAG()
    broken_node = DAGNode(_BrokenStep(), "broken", workdir_path=str(stale))
    src_node = DAGNode(_ConstantStep(img), "src")
    dag.add_node(src_node)
    dag.add_node(broken_node)
    dag.connect("src", "broken", "image")

    execute(dag)

    assert not stale.exists()
