"""Kick polygons — radial arrangement of she-kick image copies around a center origin."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from sketchbook import Sketch
from sketchbook.core.profile import ExecutionProfile
from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image

from sketches import SITE_BUNDLE


class KickPolygons(Sketch):

    name = "kick-polygons"
    description = "radial arrangement of image copies forming polygon patterns."
    date = "2026-04-11"

    def build(self, profile: ExecutionProfile) -> None:
        """Load she-kick and compose radial polygon arrangement."""
        photo = self.source(
            "photo",
            "assets/she-kick.png",
            loader=lambda p: Image(cv2.imread(str(p), cv2.IMREAD_UNCHANGED)),
        )
        thumb = photo.pipe(
            Downscale,
            params={"scale": {"min": 0.05, "max": 1.0, "step": 0.05}},
        )
        result = thumb.pipe(
            RadialArrange,
            params={
                "n": {"min": 0, "max": 100, "step": 1},
                "offset": {"min": -180.0, "max": 180.0, "step": 1.0},
                "s_rotation": {"min": -180.0, "max": 180.0, "step": 1.0},
                "s_radial": {"min": -2.0, "max": 2.0, "step": 0.01},
                "s_flip_h": {},
                "s_flip_v": {},
            },
        )
        self.output_bundle(
            result,
            SITE_BUNDLE,
            ["dress-star", "fist-pinwheel", "sun-pinwheel", "thirteen-fist-fin"],
        )


class Downscale(PipelineStep):
    """Scale the image to 25% of its original size."""

    def setup(self) -> None:
        """Declare image input and scale parameter."""
        self.add_input("image", Image)
        self.add_param("scale", float, default=0.25, debounce=150, min=0.05, max=1.0, step=0.05)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Return the image scaled by the given factor."""
        src = inputs["image"].data
        h, w = src.shape[:2]
        scale: float = params["scale"]
        result = cv2.resize(
            src, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA
        )
        return Image(result)


class RadialArrange(PipelineStep):
    """Place n copies of an image radiating outward from the center origin.

    The coordinate system has its origin at the canvas center, with (1, 0)
    at the right edge. Each copy is placed from (0, 0) outward along the
    boundary angle of its angular segment. The image is pre-rotated 90°
    clockwise so it faces toward the origin in its default position.
    """

    def setup(self) -> None:
        """Declare image input and n parameter."""
        self.add_input("image", Image)
        self.add_param("n", int, default=6, debounce=150, min=0, max=16, step=1)
        self.add_param(
            "offset", float, default=0.0, debounce=150, min=-180.0, max=180.0, step=1.0
        )
        self.add_param(
            "s_rotation", float, default=0.0, debounce=150, min=-180.0, max=180.0, step=1.0
        )
        self.add_param(
            "s_radial", float, default=0.0, debounce=150, min=-2.0, max=2.0, step=0.05
        )
        self.add_param("s_flip_h", bool, default=False)
        self.add_param("s_flip_v", bool, default=False)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Draw n copies of the image at equal angular intervals."""
        src = inputs["image"].data  # BGRA
        n: int = params["n"]
        offset: float = params["offset"]
        s_rotation: float = params["s_rotation"]
        s_radial: float = params["s_radial"]
        s_flip_h: bool = params["s_flip_h"]
        s_flip_v: bool = params["s_flip_v"]

        sh, sw = src.shape[:2]

        if n == 0:
            canvas_size = int(max(sh, sw) * 2)
            return Image(np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8))

        # Scale source so its width fills exactly 1 unit (center to edge).
        # unit is the scale reference; canvas_size is determined after rotation.
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
            stamp, rot_mat, (new_w, new_h),
            flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT,
        )
        pr_h, pr_w = src_prerot.shape[:2]

        # Radial shift in pixels: positive = outward, negative = inward.
        radial_px = int(s_radial * pr_w)

        # Canvas half must fit the stamp at its shifted position and centered vertically.
        # Stamp occupies x in [cx + radial_px, cx + radial_px + pr_w], so:
        #   cx >= pr_w + radial_px  (right edge fits)
        #   cx >= -radial_px        (left edge fits when shifted inward)
        #   cx >= pr_h // 2         (vertical centering fits)
        canvas_half = max(pr_w + radial_px, -radial_px, (pr_h + 1) // 2)
        canvas_size = canvas_half * 2
        cx = canvas_half
        cy = canvas_half

        canvas = np.zeros((canvas_size, canvas_size, 3), dtype=np.uint8)

        for i in range(n - 1, -1, -1):
            angle_deg = i * 360.0 / n + offset

            # Stamp the pre-rotated image into a blank canvas:
            #   left edge at (cx + radial_px, cy), vertically centered on cy
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

            # Rotate the whole stamp around the canvas center
            rot_mat = cv2.getRotationMatrix2D((float(cx), float(cy)), -angle_deg, 1.0)
            rotated = cv2.warpAffine(
                tmp,
                rot_mat,
                (canvas_size, canvas_size),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
            )

            # Alpha-composite the rotated copy over the canvas
            alpha = rotated[:, :, 3].astype(np.float32) / 255.0
            for c in range(3):
                canvas[:, :, c] = np.clip(
                    canvas[:, :, c].astype(np.float32) * (1.0 - alpha)
                    + rotated[:, :, c].astype(np.float32) * alpha,
                    0,
                    255,
                ).astype(np.uint8)

        return Image(canvas)
