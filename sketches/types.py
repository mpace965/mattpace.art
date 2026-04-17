"""Userland value types for sketches."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np


class Image:
    """An OpenCV image that satisfies SketchValueProtocol.

    Dev mode: PNG with no compression (fast preview).
    Build mode: PNG with maximum compression (smaller output).
    """

    extension = "png"
    kind = "image"

    def __init__(self, array: np.ndarray) -> None:
        self._array = array

    @staticmethod
    def load(path: Path) -> Image:
        """Load an image from *path* using OpenCV."""
        arr = cv2.imread(str(path))
        if arr is None:
            raise FileNotFoundError(f"cv2.imread returned None for {path}")
        return Image(arr)

    def to_bytes(self, mode: Literal["dev", "build"]) -> bytes:
        """Encode to PNG bytes. Dev: no compression. Build: max compression."""
        compress = 0 if mode == "dev" else 9
        ok, buf = cv2.imencode(".png", self._array, [cv2.IMWRITE_PNG_COMPRESSION, compress])
        if not ok:
            raise RuntimeError("cv2.imencode failed")
        return buf.tobytes()

    def to_html(self, url: str) -> str:
        """Return a minimal HTML img tag."""
        return f'<img src="{url}">'

    @property
    def array(self) -> np.ndarray:
        """Return the underlying numpy array."""
        return self._array


@dataclass
class Color:
    """An RGB color value backed by a hex string (e.g. '#ff69b4')."""

    r: int
    g: int
    b: int

    def __init__(self, value: str) -> None:
        """Parse a '#rrggbb' hex string into r, g, b components."""
        v = value.strip()
        if not (v.startswith("#") and len(v) == 7):
            raise ValueError(f"Color value must be a '#rrggbb' hex string, got: {value!r}")
        try:
            self.r = int(v[1:3], 16)
            self.g = int(v[3:5], 16)
            self.b = int(v[5:7], 16)
        except ValueError:
            raise ValueError(f"Color value must be a '#rrggbb' hex string, got: {value!r}")

    def __str__(self) -> str:
        """Return the lowercase '#rrggbb' hex representation."""
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def to_bgr(self) -> tuple[int, int, int]:
        """Return the color as a (blue, green, red) tuple for use with OpenCV."""
        return (self.b, self.g, self.r)

    def to_tweakpane(self) -> str:
        """Return the hex string representation for Tweakpane."""
        return str(self)
