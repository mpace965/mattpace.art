"""Fence Torn Paper — Canny edge detection on a weathered fence with torn paper."""

from __future__ import annotations

from typing import Annotated

import cv2
import numpy as np
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step

from sketches import SITE_BUNDLE
from sketches.types import Color, Image


@sketch(date="2026-03-29")
def fence_torn_paper() -> None:
    """weathered fence with torn paper and emphasized edges."""
    photo = source(
        "assets/fence-torn-paper.png",
        Image.load,
    )
    blurred = gaussian_blur(photo)
    edges = canny_edge(blurred)
    result = canny_composite(photo, edges)
    output(result, SITE_BUNDLE)


@step
def gaussian_blur(
    image: Image,
    *,
    kernel: Annotated[int, Param(min=1, max=31, step=2, debounce=150)] = 5,
    sigma: Annotated[float, Param(min=0.0, max=10.0, step=0.1, debounce=150)] = 1.4,
) -> Image:
    """Return the Gaussian-blurred image."""
    k = kernel if kernel % 2 == 1 else kernel + 1
    return Image(cv2.GaussianBlur(image.array, (k, k), sigma))


@step
def canny_edge(
    image: Image,
    *,
    low: Annotated[int, Param(min=0, max=500, step=1, debounce=150)] = 50,
    high: Annotated[int, Param(min=0, max=500, step=1, debounce=150)] = 150,
) -> Image:
    """Return the Canny edge mask as a single-channel image."""
    src = image.array
    gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY) if src.ndim == 3 else src
    return Image(cv2.Canny(gray, low, high))


@step
def canny_composite(
    source_img: Image,
    edges: Image,
    *,
    weight: Annotated[int, Param(min=1, max=21, step=2, debounce=150)] = 1,
    color: Annotated[Color, Param(debounce=150)] = Color("#ff69b4"),
) -> Image:
    """Return source image with colored edges composited on top."""
    src = source_img.array
    mask = edges.array
    if weight > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (weight, weight))
        mask = cv2.dilate(mask, kernel)
    color_layer = np.full_like(src, color.to_bgr(), dtype=np.uint8)
    edge_mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    result = np.where(edge_mask_3ch > 0, color_layer, src)
    return Image(result.astype(np.uint8))
