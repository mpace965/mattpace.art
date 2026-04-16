"""Cardboard v3 — greyscale cardboard texture with a tunable brightness step.

A v3 sketch to exercise param wiring: source → downscale → brightness → output.
"""

from __future__ import annotations

from typing import Annotated

import cv2
import numpy as np
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, SketchContext, sketch, step

from sketches import SITE_BUNDLE
from sketches.types import Image


@step
def brightness(
    image: Image,
    *,
    level: Annotated[int, Param(min=0, max=255, step=1, debounce=100)] = 128,
) -> Image:
    """Shift image brightness by (level - 128), clamped to [0, 255]."""
    delta = int(level) - 128
    shifted = image.array.astype(np.int16) + delta
    clamped = np.clip(shifted, 0, 255).astype(np.uint8)
    return Image(clamped)


@step
def downscale_factor(ctx: SketchContext) -> float:
    """Return 0.5 in dev mode, 1.0 in build mode."""
    return 0.5 if ctx.mode == "dev" else 1.0


@step
def downscale(image: Image, scale: float) -> Image:
    """Resize image by scale factor using area interpolation."""
    h, w = image.array.shape[:2]
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    resized = cv2.resize(image.array, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return Image(resized)


@sketch(date="2026-04-14")
def cardboard_v3() -> None:
    """Cardboard texture — v3 walking skeleton."""
    img = source("assets/cardboard.jpg", Image.load)
    scale = downscale_factor()
    small = downscale(img, scale)
    result = brightness(small)
    output(result, SITE_BUNDLE)
