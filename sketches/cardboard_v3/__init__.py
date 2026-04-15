"""Cardboard v3 — greyscale cardboard texture with a tunable brightness step.

A v3 sketch to exercise param wiring: source → brightness → output.
"""

from __future__ import annotations

from typing import Annotated

import numpy as np

from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step

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


@sketch(date="2026-04-14")
def cardboard_v3() -> None:
    """Cardboard texture — v3 walking skeleton."""
    img = source("assets/cardboard.jpg", Image.load)
    result = brightness(img)
    output(result, "main")
