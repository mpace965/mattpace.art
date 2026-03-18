"""Canny edge detection step."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image


class EdgeDetect(PipelineStep):
    """Apply Canny edge detection to an image, with an optional mask."""

    def setup(self) -> None:
        """Declare image input, optional mask input, and threshold parameters."""
        self.add_input("image", Image)
        self.add_input("mask", Image, optional=True)
        self.add_param("low_threshold", float, default=100.0, debounce=150, min=0, max=500, step=1.0)
        self.add_param("high_threshold", float, default=200.0, debounce=150, min=0, max=500, step=1.0)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Run Canny edge detection and return the result as a 3-channel image.

        If a mask input is provided, the edges are masked so only the white
        regions of the mask remain visible.
        """
        image: Image = inputs["image"]
        gray = cv2.cvtColor(image.data, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, params["low_threshold"], params["high_threshold"])
        result = np.stack([edges, edges, edges], axis=-1)

        mask: Image | None = inputs.get("mask")
        if mask is not None:
            mask_gray = cv2.cvtColor(mask.data, cv2.COLOR_BGR2GRAY)
            _, mask_binary = cv2.threshold(mask_gray, 128, 255, cv2.THRESH_BINARY)
            result = cv2.bitwise_and(result, result, mask=mask_binary)

        return Image(result)
