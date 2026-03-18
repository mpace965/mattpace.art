"""Weighted blend of two images."""

from __future__ import annotations

from typing import Any

import cv2

from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image


class Blend(PipelineStep):
    """Blend two images using a weighted average (cv2.addWeighted)."""

    def setup(self) -> None:
        """Declare base and overlay inputs plus a blend weight parameter."""
        self.add_input("image", Image)
        self.add_input("overlay", Image)
        self.add_param("weight", float, default=0.5, debounce=150, min=0.0, max=1.0, step=0.01)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Return a weighted blend of image and overlay, resizing overlay if needed."""
        base = inputs["image"].data
        overlay = inputs["overlay"].data

        if overlay.shape[:2] != base.shape[:2]:
            overlay = cv2.resize(overlay, (base.shape[1], base.shape[0]))

        w = params["weight"]
        blended = cv2.addWeighted(base, 1.0 - w, overlay, w, 0)
        return Image(blended)
