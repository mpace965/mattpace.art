"""Gaussian blur step."""

from __future__ import annotations

from typing import Any

import cv2

from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image


class GaussianBlur(PipelineStep):
    """Apply Gaussian blur to an image."""

    def setup(self) -> None:
        """Declare image input and sigma parameter."""
        self.add_input("image", Image)
        self.add_param("sigma", float, default=1.0, debounce=150, min=0.1, max=20.0, step=0.1)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Blur the image using a Gaussian kernel sized automatically from sigma."""
        blurred = cv2.GaussianBlur(inputs["image"].data, (0, 0), sigmaX=params["sigma"])
        return Image(blurred)
