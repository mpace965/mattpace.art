"""Userland value types for v3 sketches."""

from __future__ import annotations

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
