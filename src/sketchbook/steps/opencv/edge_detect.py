"""Canny edge detection step."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image


class EdgeDetect(PipelineStep):
    """Apply Canny edge detection to an image."""

    def setup(self) -> None:
        """Declare image input and threshold parameters."""
        self.add_input("image", Image)
        self.add_param("low_threshold", float, default=100.0, debounce=150, min=0, max=500, step=1.0)
        self.add_param("high_threshold", float, default=200.0, debounce=150, min=0, max=500, step=1.0)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Run Canny edge detection and return the result as a 3-channel image."""
        image: Image = inputs["image"]
        gray = cv2.cvtColor(image.data, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, params["low_threshold"], params["high_threshold"])
        result = np.stack([edges, edges, edges], axis=-1)
        return Image(result)
