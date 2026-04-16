"""Cardboard — greyscale cardboard texture with a grid of inverted circles."""

from __future__ import annotations

from typing import Annotated

import cv2
import numpy as np
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step

from sketches import SITE_BUNDLE
from sketches.types import Image


@sketch(date="2026-03-09")
def cardboard() -> None:
    """greyscale cardboard texture with a grid of inverted circles."""
    img = source("assets/cardboard.jpg", Image.load)
    mask = circle_grid_mask(img)
    result = difference_blend(img, mask)
    output(result, SITE_BUNDLE, presets=["nine"])


@step
def circle_grid_mask(
    image: Image,
    *,
    count: Annotated[int, Param(min=1, max=20, step=1, debounce=150)] = 3,
    radius: Annotated[float, Param(min=0.0, max=1.0, step=0.01, debounce=150)] = 0.75,
) -> Image:
    """Draw a uniform grid of filled white circles on a black background."""
    src = image.array
    h, w = src.shape[:2]
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    cell_w = w / count
    cell_h = h / count
    for row in range(count):
        for col in range(count):
            cx = int((col + 0.5) * cell_w)
            cy = int((row + 0.5) * cell_h)
            r = int(min(cell_w, cell_h) * radius / 2)
            cv2.circle(canvas, (cx, cy), r, (255, 255, 255), thickness=-1)
    return Image(canvas)


@step
def difference_blend(image: Image, mask: Image) -> Image:
    """Return the per-pixel absolute difference of image and mask."""
    return Image(cv2.absdiff(image.array, mask.array))
