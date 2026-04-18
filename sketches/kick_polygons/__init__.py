"""Kick polygons — radial arrangement of she-kick image copies around a center origin."""

from __future__ import annotations

from typing import Annotated

import cv2
import numpy as np
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, SketchContext, sketch, step

from sketches import SITE_BUNDLE
from sketches.types import Image


@sketch(date="2026-04-11")
def kick_polygons() -> None:
    """radial arrangement of image copies forming polygon patterns."""
    photo = source(
        "assets/she-kick.png",
        lambda p: Image(cv2.imread(str(p), cv2.IMREAD_UNCHANGED)),
    )
    scale = downscale_factor()
    thumb = downscale(photo, scale)
    result = radial_arrange(thumb)
    output(
        result,
        SITE_BUNDLE,
        presets=["dress-star", "fist-pinwheel", "sun-pinwheel", "thirteen-fist-fin"],
    )


@step
def downscale_factor(ctx: SketchContext) -> float:
    """Return 0.25 in dev mode, 0.5 in build mode."""
    return 0.25 if ctx.mode == "dev" else 0.5


@step
def downscale(image: Image, scale: float) -> Image:
    """Return the image scaled by scale factor using area interpolation."""
    src = image.array
    h, w = src.shape[:2]
    result = cv2.resize(
        src,
        (max(1, int(w * scale)), max(1, int(h * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return Image(result)


@step
def radial_arrange(
    image: Image,
    *,
    n: Annotated[int, Param(min=0, max=100, step=1, debounce=150)] = 6,
    offset: Annotated[float, Param(min=-180.0, max=180.0, step=1.0, debounce=150)] = 0.0,
    s_rotation: Annotated[float, Param(min=-180.0, max=180.0, step=1.0, debounce=150)] = 0.0,
    s_radial: Annotated[float, Param(min=-2.0, max=2.0, step=0.05, debounce=150)] = 0.0,
    s_flip_h: Annotated[bool, Param()] = False,
    s_flip_v: Annotated[bool, Param()] = False,
) -> Image:
    """Place n copies of an image radiating outward from the center origin."""
    src = image.array  # BGRA
    sh, sw = src.shape[:2]

    if n == 0:
        canvas_size = int(max(sh, sw) * 2)
        return Image(np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8))

    # Scale source so its width fills exactly 1 unit (center to edge).
    unit = max(sh, sw)
    scale = unit / sw
    scaled_w = max(1, int(sw * scale))
    scaled_h = max(1, int(sh * scale))
    src_scaled = cv2.resize(src, (scaled_w, scaled_h), interpolation=cv2.INTER_LANCZOS4)

    # Apply stamp transforms: flip then rotate around the image center.
    stamp = src_scaled
    if s_flip_h:
        stamp = cv2.flip(stamp, 1)
    if s_flip_v:
        stamp = cv2.flip(stamp, 0)
    pre_h, pre_w = stamp.shape[:2]
    angle_rad = np.deg2rad(s_rotation)
    cos_a = abs(np.cos(angle_rad))
    sin_a = abs(np.sin(angle_rad))
    new_w = int(np.ceil(pre_w * cos_a + pre_h * sin_a))
    new_h = int(np.ceil(pre_w * sin_a + pre_h * cos_a))
    rot_mat = cv2.getRotationMatrix2D((pre_w / 2.0, pre_h / 2.0), -s_rotation, 1.0)
    rot_mat[0, 2] += (new_w - pre_w) / 2.0
    rot_mat[1, 2] += (new_h - pre_h) / 2.0
    src_prerot = cv2.warpAffine(
        stamp,
        rot_mat,
        (new_w, new_h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
    )
    pr_h, pr_w = src_prerot.shape[:2]

    # Radial shift in pixels: positive = outward, negative = inward.
    radial_px = int(s_radial * pr_w)

    canvas_half = max(pr_w + radial_px, -radial_px, (pr_h + 1) // 2)
    canvas_size = canvas_half * 2
    cx = canvas_half
    cy = canvas_half

    canvas = np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8)

    for i in range(n - 1, -1, -1):
        angle_deg = i * 360.0 / n + offset

        tmp = np.zeros((canvas_size, canvas_size, 4), dtype=np.uint8)

        x0 = cx + radial_px
        y0 = cy - pr_h // 2

        sx = max(0, -x0)
        sy = max(0, -y0)
        ex = min(pr_w, canvas_size - x0)
        ey = min(pr_h, canvas_size - y0)

        if ex > sx and ey > sy:
            dx = max(0, x0)
            dy = max(0, y0)
            tmp[dy : dy + (ey - sy), dx : dx + (ex - sx)] = src_prerot[sy:ey, sx:ex]

        rot_mat = cv2.getRotationMatrix2D((float(cx), float(cy)), -angle_deg, 1.0)
        rotated = cv2.warpAffine(
            tmp,
            rot_mat,
            (canvas_size, canvas_size),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )

        alpha = rotated[:, :, 3].astype(np.float32) / 255.0
        for c in range(3):
            canvas[:, :, c] = np.clip(
                canvas[:, :, c].astype(np.float32) * (1.0 - alpha)
                + rotated[:, :, c].astype(np.float32) * alpha,
                0,
                255,
            ).astype(np.uint8)

    return Image(canvas)
