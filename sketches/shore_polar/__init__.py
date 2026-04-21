"""Shore polar — polar/depolar kaleidoscope over the rocky shore."""

from __future__ import annotations

from typing import Annotated

from wand.image import Image as WandImage

import sketches.wand_compat  # noqa: F401 — patches WandImage for SketchValueProtocol
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, SketchContext, sketch, step

from sketches import SITE_BUNDLE


@sketch(date="2026-04-19")
def shore_polar() -> None:
    """polar/depolar kaleidoscope over the rocky shore."""
    photo = source("assets/shore.png", lambda p: WandImage(filename=str(p)))
    square = crop_square(photo)
    size = work_size()
    scaled = downscale(square, size)
    rotated = rotate(scaled)
    strip = unwrap(rotated)
    tiled = mirror_tile(strip)
    result = rewrap(tiled)


@step
def crop_square(
    image: WandImage,
    *,
    cx: Annotated[float, Param(min=0.0, max=1.0, step=0.01, debounce=300)] = 0.5,
    cy: Annotated[float, Param(min=0.0, max=1.0, step=0.01, debounce=300)] = 0.5,
    size: Annotated[float, Param(min=0.1, max=1.0, step=0.01, debounce=300)] = 1.0,
) -> WandImage:
    """Crop to a square; cx/cy are fractional center, size is fraction of the shorter side."""
    side = round(min(image.width, image.height) * size)
    left = round(image.width * cx - side / 2)
    top = round(image.height * cy - side / 2)
    left = max(0, min(left, image.width - side))
    top = max(0, min(top, image.height - side))
    result = image.clone()
    result.crop(left, top, width=side, height=side)
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
    # Canvas sized exactly to filled pixels — avoids a black-pixel seam at the wrap edge
    canvas_w = seg_w * segments
    with strip.clone() as seg:
        seg.crop(0, 0, width=seg_w, height=strip.height)
        with seg.clone() as mirror:
            mirror.flop()
            canvas = WandImage(width=canvas_w, height=strip.height, background="black")
            for i in range(segments):
                tile = mirror if i % 2 else seg
                canvas.composite(tile, left=i * seg_w, top=0)
    return canvas


@step
def rotate(
    image: WandImage,
    *,
    degrees: Annotated[float, Param(min=0.0, max=360.0, step=1.0, debounce=300)] = 0.0,
) -> WandImage:
    """Rotate the image by the given degrees."""
    result = image.clone()
    result.rotate(degrees)
    return result


@step
def work_size(ctx: SketchContext) -> int:
    """Return 1024 in dev mode, 4096 in build mode."""
    return 1024 if ctx.mode == "dev" else 4096


@step
def downscale(image: WandImage, max_side: int) -> WandImage:
    """Resize so the longest side is at most max_side, preserving aspect ratio."""
    if image.width <= max_side and image.height <= max_side:
        return image.clone()
    scale = max_side / max(image.width, image.height)
    result = image.clone()
    result.resize(round(image.width * scale), round(image.height * scale))
    return result


@step
def rewrap(strip: WandImage) -> WandImage:
    """Polar: re-wrap the tiled strip into a circular kaleidoscope."""
    result = strip.clone()
    result.virtual_pixel = "mirror"
    result.distort("polar", [0])
    return result
