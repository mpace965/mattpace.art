"""Cardboard Stripes — cardboard texture with DIFFERENCE-blended horizontal stripes."""

from __future__ import annotations

import math
from typing import Annotated, Any

import cv2
import numpy as np
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step

from sketches import SITE_BUNDLE
from sketches.types import Image

_WIDTH_FNS: dict[str, Any] = {
    "uniform": lambda i, n: 1.0,
    "linear": lambda i, n: i / (n - 1) if n > 1 else 1.0,
    "exponential": lambda i, n: (math.exp(i / (n - 1)) - 1) / (math.e - 1) if n > 1 else 1.0,
    "sinusoidal": lambda i, n: math.sin(math.pi * i / (n - 1)) if n > 1 else 1.0,
}

_WIDTH_FN_OPTIONS = list(_WIDTH_FNS.keys())
_ALIGN_OPTIONS = ["left", "center", "right"]


@sketch(date="2026-03-12")
def cardboard_stripes() -> None:
    """greyscale cardboard texture with a stack of inverted horizontal bars."""
    img = source("assets/cardboard.jpg", Image.load)
    mask = stripes_mask(img)
    result = difference_blend(img, mask)
    output(result, SITE_BUNDLE, presets=["three", "steps"])


@step
def stripes_mask(
    image: Image,
    *,
    count: Annotated[int, Param(min=1, max=50, step=1, debounce=150)] = 3,
    vert_margin: Annotated[float, Param(min=0.0, max=1.0, step=0.01, debounce=150)] = 0.45,
    horz_margin: Annotated[float, Param(min=0.0, max=1.0, step=0.01, debounce=150)] = 0.2,
    width_fn: Annotated[str, Param(options=_WIDTH_FN_OPTIONS)] = "uniform",
    invert_fn: Annotated[bool, Param()] = False,
    align: Annotated[str, Param(options=_ALIGN_OPTIONS)] = "center",
) -> Image:
    """Draw horizontal white rectangles on a black canvas with the configured layout."""
    src = image.array
    h, w = src.shape[:2]
    inset = horz_margin * 0.5 * w
    available_w = w - 2 * inset
    total_gap = vert_margin * h
    gap = total_gap / (count + 1)
    rect_h = (h - total_gap) / count
    fn = _WIDTH_FNS[width_fn]
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


@step
def difference_blend(image: Image, mask: Image) -> Image:
    """Return the per-pixel absolute difference of image and mask."""
    img = image.array
    msk = mask.array
    if img.shape != msk.shape:
        msk = cv2.resize(msk, (img.shape[1], img.shape[0]))
    return Image(cv2.absdiff(img, msk))


def _lerp(t: float, a: float, b: float) -> float:
    """Linearly interpolate between a and b by t."""
    return a + t * (b - a)
