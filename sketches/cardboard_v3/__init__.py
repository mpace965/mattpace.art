"""Cardboard v3 — greyscale cardboard texture with a passthrough step.

A minimal v3 sketch to exercise the walking skeleton: source → passthrough → output.
"""

from __future__ import annotations

from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import sketch, step

from sketches.types import Image


@step
def passthrough(image: Image) -> Image:
    """Return the image unchanged."""
    return image


@sketch(date="2026-04-14")
def cardboard_v3() -> None:
    """Cardboard texture — v3 walking skeleton."""
    img = source("assets/cardboard.jpg", Image.load)
    result = passthrough(img)
    output(result, "main")
