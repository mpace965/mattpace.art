"""Fence Torn Paper — Canny edge detection on a weathered fence with torn paper."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from sketchbook import Sketch
from sketchbook.core.params import Color
from sketchbook.core.profile import ExecutionProfile
from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image

from sketches import SITE_BUNDLE


class FenceTornPaper(Sketch):
    """Canny edge detection composited in hot pink over the source photo."""

    name = "fence-torn-paper"
    description = "weathered fence with torn paper and emphasized edges."
    date = "2026-03-29"

    def build(self, profile: ExecutionProfile) -> None:
        """Load source, blur, detect edges, then composite hot-pink edges over original."""
        photo = self.source(
            "photo",
            "assets/fence-torn-paper.png",
            loader=lambda p: Image(cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)),
        )
        blurred = photo.pipe(
            GaussianBlur,
            params={
                "kernel": {"min": 1, "max": 31, "step": 2},
                "sigma": {"min": 0.0, "max": 10.0, "step": 0.1},
            },
        )
        edges = blurred.pipe(
            CannyEdge,
            params={
                "low": {"min": 0, "max": 500, "step": 1},
                "high": {"min": 0, "max": 500, "step": 1},
            },
        )
        composite = self.add(
            CannyComposite,
            inputs={"source": photo, "edges": edges},
            params={
                "weight": {"min": 1, "max": 21, "step": 2},
                "color": {},
            },
        )
        self.output_bundle(composite, SITE_BUNDLE)


class GaussianBlur(PipelineStep):
    """Apply a Gaussian blur to reduce noise before edge detection."""

    def setup(self) -> None:
        """Declare image input and blur parameters."""
        self.add_input("image", Image)
        self.add_param("kernel", int, default=5, debounce=150, min=1, max=31, step=2)
        self.add_param("sigma", float, default=1.4, debounce=150, min=0.0, max=10.0, step=0.1)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Return the Gaussian-blurred image."""
        src = inputs["image"].data
        k = params["kernel"]
        if k % 2 == 0:
            k += 1
        result = cv2.GaussianBlur(src, (k, k), params["sigma"])
        return Image(result)


class CannyEdge(PipelineStep):
    """Detect edges using the Canny algorithm and return a binary mask."""

    def setup(self) -> None:
        """Declare image input and Canny threshold parameters."""
        self.add_input("image", Image)
        self.add_param("low", int, default=50, debounce=150, min=0, max=500, step=1)
        self.add_param("high", int, default=150, debounce=150, min=0, max=500, step=1)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Return the Canny edge mask as a single-channel image."""
        src = inputs["image"].data
        gray = cv2.cvtColor(src, cv2.COLOR_RGB2GRAY) if src.ndim == 3 else src
        edges = cv2.Canny(gray, params["low"], params["high"])
        return Image(edges)


class CannyComposite(PipelineStep):
    """Composite hot-pink Canny edges over the source image."""

    def setup(self) -> None:
        """Declare source and edge mask inputs, stroke weight and edge color parameters."""
        self.add_input("source", Image)
        self.add_input("edges", Image)
        self.add_param("weight", int, default=1, debounce=150, min=1, max=21, step=2)
        self.add_param("color", Color, default=Color("#ff69b4"), debounce=150)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Return source image with colored edges composited on top."""
        src = inputs["source"].data
        mask = inputs["edges"].data

        weight = params["weight"]
        if weight > 1:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (weight, weight))
            mask = cv2.dilate(mask, kernel)

        color: Color = params["color"]
        color_layer = np.full_like(src, (color.r, color.g, color.b), dtype=np.uint8)
        edge_mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        result = np.where(edge_mask_3ch > 0, color_layer, src)
        return Image(result.astype(np.uint8), compress_level=9)
