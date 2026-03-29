"""Cardboard Stripes — cardboard texture with DIFFERENCE-blended horizontal stripes."""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np
from sketchbook import Sketch
from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image

from sketches import SITE_BUNDLE

_WIDTH_FNS: dict[str, Any] = {
    "uniform": lambda i, n: 1.0,
    "linear": lambda i, n: i / (n - 1) if n > 1 else 1.0,
    "exponential": lambda i, n: (math.exp(i / (n - 1)) - 1) / (math.e - 1) if n > 1 else 1.0,
    "sinusoidal": lambda i, n: math.sin(math.pi * i / (n - 1)) if n > 1 else 1.0,
}

_WIDTH_FN_OPTIONS = list(_WIDTH_FNS.keys())
_ALIGN_OPTIONS = ["left", "center", "right"]


class CardboardStripes(Sketch):
    """Cardboard texture with DIFFERENCE-blended rectangle stripes."""

    name = "cardboard-stripes"
    description = "greyscale cardboard texture with a stack of inverted horizontal bars."
    date = "2026-03-12"

    def build(self) -> None:
        """Load cardboard photo, generate a stripe mask, and apply DIFFERENCE blend."""
        photo = self.source("photo", "assets/cardboard.jpg", loader=lambda p: Image(cv2.imread(str(p))))
        mask = photo.pipe(StripesMask)
        blended = self.add(DifferenceBlend, inputs={"image": photo, "mask": mask})
        self.output_bundle(blended, SITE_BUNDLE, presets=["three", "steps"])


class StripesMask(PipelineStep):
    """Generate a white-on-black stripe mask matching the input image dimensions."""

    def setup(self) -> None:
        """Declare image input for sizing and stripe layout parameters."""
        self.add_input("image", Image)
        self.add_param("count", int, default=3, debounce=150, min=1, max=50, step=1)
        self.add_param(
            "vert_margin", float, default=0.45, debounce=150, min=0.0, max=1.0, step=0.01
        )
        self.add_param("horz_margin", float, default=0.2, debounce=150, min=0.0, max=1.0, step=0.01)
        self.add_param("width_fn", str, default="uniform", options=_WIDTH_FN_OPTIONS)
        self.add_param("invert_fn", bool, default=False)
        self.add_param("align", str, default="center", options=_ALIGN_OPTIONS)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Draw horizontal white rectangles on a black canvas with the configured layout."""
        src = inputs["image"].data
        h, w = src.shape[:2]

        count: int = params["count"]
        vert_margin: float = params["vert_margin"]
        horz_margin: float = params["horz_margin"]
        width_fn_key: str = params["width_fn"]
        invert_fn: bool = params["invert_fn"]
        align: str = params["align"]

        inset = horz_margin * 0.5 * w
        available_w = w - 2 * inset

        total_gap = vert_margin * h
        gap = total_gap / (count + 1)
        rect_h = (h - total_gap) / count

        fn = _WIDTH_FNS[width_fn_key]

        canvas = np.zeros((h, w, 3), dtype=np.uint8)

        for i in range(count):
            raw = fn(i, count)
            v = (1.0 - raw) if invert_fn else raw
            rect_w = available_w * _lerp(v, 1.0 / count, 1.0)
            if align == "left":
                x = inset
            elif align == "right":
                x = inset + available_w - rect_w
            else:
                x = inset + (available_w - rect_w) / 2
            y = gap + i * (rect_h + gap)
            cv2.rectangle(
                canvas,
                (int(x), int(y)),
                (int(x + rect_w), int(y + rect_h)),
                (255, 255, 255),
                thickness=-1,
            )

        return Image(canvas)


class DifferenceBlend(PipelineStep):
    """Blend two images using the DIFFERENCE operation (absolute difference)."""

    def setup(self) -> None:
        """Declare image and mask inputs."""
        self.add_input("image", Image)
        self.add_input("mask", Image)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Return the per-pixel absolute difference of image and mask."""
        img = inputs["image"].data
        mask = inputs["mask"].data
        # Resize mask to match image if needed
        if img.shape != mask.shape:
            mask = cv2.resize(mask, (img.shape[1], img.shape[0]))
        return Image(cv2.absdiff(img, mask))


def _lerp(t: float, a: float, b: float) -> float:
    """Linearly interpolate between a and b by t."""
    return a + t * (b - a)
