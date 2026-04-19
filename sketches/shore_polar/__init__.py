"""Shore polar — polar/depolar kaleidoscope over the rocky shore."""

from __future__ import annotations

from typing import Annotated

from wand.image import Image as WandImage

import sketches.wand_compat  # noqa: F401 — patches WandImage for SketchValueProtocol
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step

from sketches import SITE_BUNDLE


@sketch(date="2026-04-19")
def shore_polar() -> None:
    """polar/depolar kaleidoscope over the rocky shore."""
    photo = source("assets/shore.png", lambda p: WandImage(filename=str(p)))
    square = crop_square(photo)
    strip = unwrap(square)
    tiled = mirror_tile(strip)
    result = rewrap(tiled)


@step
def crop_square(image: WandImage) -> WandImage:
    """Crop to a centered square."""
    size = min(image.width, image.height)
    left = (image.width - size) // 2
    top = (image.height - size) // 2
    result = image.clone()
    result.crop(left, top, width=size, height=size)
    return result


@step
def unwrap(
    image: WandImage,
    *,
    scale: Annotated[float, Param(min=0.1, max=1.0, step=0.05, debounce=300)] = 1.0,
) -> WandImage:
    """Depolar: unwrap the image from polar coordinates to a rectangular strip."""
    result = image.clone()
    result.virtual_pixel = "mirror"
    rmax = (min(result.width, result.height) / 2) * scale
    result.distort("depolar", [rmax])
    return result


@step
def mirror_tile(
    strip: WandImage,
    *,
    segments: Annotated[int, Param(min=2, max=32, step=2, debounce=300)] = 8,
) -> WandImage:
    """Mirror-tile the strip to create radial symmetry before re-wrapping."""
    seg_w = strip.width // segments
    with strip.clone() as seg:
        seg.crop(0, 0, width=seg_w, height=strip.height)
        with seg.clone() as mirror:
            mirror.flop()
            canvas = WandImage(width=strip.width, height=strip.height, background="black")
            for i in range(segments):
                tile = mirror if i % 2 else seg
                canvas.composite(tile, left=i * seg_w, top=0)
    return canvas


@step
def rewrap(strip: WandImage) -> WandImage:
    """Polar: re-wrap the tiled strip into a circular kaleidoscope."""
    result = strip.clone()
    result.virtual_pixel = "mirror"
    result.distort("polar", [0])
    return result
