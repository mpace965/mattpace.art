"""Unit tests for the GaussianBlur step."""

from __future__ import annotations

import numpy as np

from sketchbook.core.types import Image
from sketchbook.steps.opencv.blur import GaussianBlur


class TestGaussianBlur:
    def test_setup_declares_sigma(self) -> None:
        step = GaussianBlur()
        assert "sigma" in step._param_registry._params

    def test_sigma_range(self) -> None:
        step = GaussianBlur()
        p = step._param_registry._params["sigma"]
        assert p.min == 0.1
        assert p.max == 20.0

    def test_process_returns_image(self) -> None:
        step = GaussianBlur()
        arr = np.zeros((64, 64, 3), dtype=np.uint8)
        result = step.process({"image": Image(arr)}, step._param_registry.values())
        assert isinstance(result, Image)

    def test_process_returns_same_shape(self) -> None:
        step = GaussianBlur()
        arr = np.zeros((64, 64, 3), dtype=np.uint8)
        result = step.process({"image": Image(arr)}, step._param_registry.values())
        assert result.data.shape == arr.shape
