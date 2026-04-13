"""Cardboard — greyscale cardboard texture with a grid of inverted circles."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from sketchbook import Sketch
from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image

from sketches import SITE_BUNDLE


class Cardboard(Sketch):
    """Cardboard texture with DIFFERENCE-blended circle grid."""

    name = "cardboard"
    description = "greyscale cardboard texture with a grid of inverted circles."
    date = "2026-03-09"

    def build(self) -> None:
        """Load the cardboard photo, generate a circle grid mask, and apply DIFFERENCE blend."""
        photo = self.source(
            "photo", "assets/cardboard.jpg", loader=lambda p: Image(cv2.imread(str(p)))
        )
        mask = photo.pipe(
            CircleGridMask,
            params={
                "count": {"min": 1, "max": 20, "step": 1},
                "radius": {"min": 0.0, "max": 1.0, "step": 0.01},
            },
        )
        blended = self.add(DifferenceBlend, inputs={"image": photo, "mask": mask})
        compress_level = 9 if self.mode == "build" else 0
        final = blended.pipe(Postprocess(compress_level))
        self.output_bundle(final, SITE_BUNDLE, presets=["nine"])


class CircleGridMask(PipelineStep):
    """Generate a white-circle-on-black mask for a given image size."""

    def setup(self) -> None:
        """Declare image input for sizing, and count/radius parameters."""
        self.add_input("image", Image)
        self.add_param("count", int, default=3, debounce=150, min=1, max=20, step=1)
        self.add_param("radius", float, default=0.75, debounce=150, min=0.0, max=1.0, step=0.01)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Draw a uniform grid of filled white circles on a black background."""
        src = inputs["image"].data
        h, w = src.shape[:2]
        count: int = params["count"]
        radius_frac: float = params["radius"]

        canvas = np.zeros((h, w, 3), dtype=np.uint8)

        cell_w = w / count
        cell_h = h / count

        for row in range(count):
            for col in range(count):
                cx = int((col + 0.5) * cell_w)
                cy = int((row + 0.5) * cell_h)
                r = int(min(cell_w, cell_h) * radius_frac / 2)
                cv2.circle(canvas, (cx, cy), r, (255, 255, 255), thickness=-1)

        return Image(canvas)


class DifferenceBlend(PipelineStep):
    """Blend two images using the DIFFERENCE operation (absolute difference)."""

    def setup(self) -> None:
        """Declare image and mask inputs."""
        self.add_input("image", Image)
        self.add_input("mask", Image)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Return the per-pixel absolute difference of image and mask."""
        result = cv2.absdiff(inputs["image"].data, inputs["mask"].data)
        return Image(result)


class Postprocess(PipelineStep):
    """Apply output-time encoding settings to the final image."""

    def __init__(self, compress_level: int) -> None:
        self._compress_level = compress_level
        super().__init__()

    def setup(self) -> None:
        """Declare image input."""
        self.add_input("image", Image)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Return the image with the configured compress level."""
        return Image(inputs["image"].data, compress_level=self._compress_level)
