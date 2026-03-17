"""Unit tests for the EdgeDetect step."""

from __future__ import annotations

import numpy as np

from sketchbook.core.types import Image
from sketchbook.steps.opencv.edge_detect import EdgeDetect


class TestEdgeDetect:
    def test_setup_declares_low_threshold(self) -> None:
        step = EdgeDetect()
        assert "low_threshold" in step._param_registry._params

    def test_setup_declares_high_threshold(self) -> None:
        step = EdgeDetect()
        assert "high_threshold" in step._param_registry._params

    def test_low_threshold_range(self) -> None:
        step = EdgeDetect()
        p = step._param_registry._params["low_threshold"]
        assert p.min == 0
        assert p.max == 500

    def test_high_threshold_range(self) -> None:
        step = EdgeDetect()
        p = step._param_registry._params["high_threshold"]
        assert p.min == 0
        assert p.max == 500

    def test_process_returns_same_shape(self) -> None:
        step = EdgeDetect()
        arr = np.zeros((64, 64, 3), dtype=np.uint8)
        image = Image(arr)
        params = step._param_registry.values()
        result = step.process({"image": image}, params)
        assert result.data.shape[:2] == (64, 64)

    def test_process_returns_image(self) -> None:
        step = EdgeDetect()
        arr = np.zeros((64, 64, 3), dtype=np.uint8)
        image = Image(arr)
        params = step._param_registry.values()
        result = step.process({"image": image}, params)
        assert isinstance(result, Image)
