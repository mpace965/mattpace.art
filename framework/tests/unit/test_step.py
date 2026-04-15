"""Unit tests for PipelineStep: add_input, setup/process contract, Passthrough output."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from sketchbook.core.step import InputSpec, PipelineStep
from sketchbook.core.types import Image
from tests.steps import Passthrough

# ---------------------------------------------------------------------------
# add_input
# ---------------------------------------------------------------------------


class _MinimalStep(PipelineStep):
    def setup(self) -> None:
        self.add_input("image", Image)
        self.add_input("mask", Image, optional=True)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> None:
        return None


def test_add_input_registers_required_input() -> None:
    step = _MinimalStep()
    assert "image" in step.input_specs
    spec = step.input_specs["image"]
    assert isinstance(spec, InputSpec)
    assert spec.type is Image
    assert spec.optional is False


def test_add_input_registers_optional_input() -> None:
    step = _MinimalStep()
    assert "mask" in step.input_specs
    assert step.input_specs["mask"].optional is True


def test_add_input_multiple_inputs() -> None:
    step = _MinimalStep()
    assert len(step.input_specs) == 2


# ---------------------------------------------------------------------------
# setup / process contract
# ---------------------------------------------------------------------------


class _NoProcess(PipelineStep):
    def setup(self) -> None:
        pass


def test_process_not_implemented_raises() -> None:
    step = _NoProcess()
    with pytest.raises(NotImplementedError, match="_NoProcess must implement process"):
        step.process({}, {})


# ---------------------------------------------------------------------------
# add_param
# ---------------------------------------------------------------------------


class _ParamStep(PipelineStep):
    def setup(self) -> None:
        self.add_param("threshold", float, default=50.0, min=0.0, max=100.0)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Any:
        return params["threshold"]


def test_add_param_registers_in_registry() -> None:
    step = _ParamStep()
    assert "threshold" in step.param_values()


def test_add_param_default_value() -> None:
    step = _ParamStep()
    assert step.param_values()["threshold"] == 50.0


def test_params_passed_to_process() -> None:
    step = _ParamStep()
    step.set_param("threshold", 77.0)
    result = step.process({}, step.param_values())
    assert result == 77.0


# ---------------------------------------------------------------------------
# Passthrough
# ---------------------------------------------------------------------------


def test_passthrough_output_equals_input() -> None:
    img = Image(np.zeros((8, 8, 3), dtype=np.uint8))
    step = Passthrough()
    result = step.process({"image": img}, {})
    assert result is img


def test_passthrough_declares_image_input() -> None:
    step = Passthrough()
    assert "image" in step.input_specs
    assert step.input_specs["image"].type is Image
    assert step.input_specs["image"].optional is False


# ---------------------------------------------------------------------------
# Optional input not required at execution time
# ---------------------------------------------------------------------------


class _OptionalStep(PipelineStep):
    """Step with one required and one optional input."""

    def setup(self) -> None:
        self.add_input("image", Image)
        self.add_input("mask", Image, optional=True)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        # Optional input should be None when not provided
        assert "mask" not in inputs or inputs["mask"] is None or isinstance(inputs["mask"], Image)
        return inputs["image"]


def test_optional_input_is_optional_flag() -> None:
    step = _OptionalStep()
    assert step.input_specs["mask"].optional is True


def test_required_input_is_not_optional() -> None:
    step = _OptionalStep()
    assert step.input_specs["image"].optional is False
