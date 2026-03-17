"""Unit tests for PipelineStep: add_input, setup/process contract, Passthrough output equals input."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from sketchbook.core.step import InputSpec, PipelineStep
from sketchbook.core.types import Image
from sketchbook.steps.passthrough import Passthrough


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
    assert "image" in step._inputs
    spec = step._inputs["image"]
    assert isinstance(spec, InputSpec)
    assert spec.type is Image
    assert spec.optional is False


def test_add_input_registers_optional_input() -> None:
    step = _MinimalStep()
    assert "mask" in step._inputs
    assert step._inputs["mask"].optional is True


def test_add_input_multiple_inputs() -> None:
    step = _MinimalStep()
    assert len(step._inputs) == 2


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
# Passthrough
# ---------------------------------------------------------------------------

def test_passthrough_output_equals_input() -> None:
    img = Image(np.zeros((8, 8, 3), dtype=np.uint8))
    step = Passthrough()
    result = step.process({"image": img}, {})
    assert result is img


def test_passthrough_declares_image_input() -> None:
    step = Passthrough()
    assert "image" in step._inputs
    assert step._inputs["image"].type is Image
    assert step._inputs["image"].optional is False
