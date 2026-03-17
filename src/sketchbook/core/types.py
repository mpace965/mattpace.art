"""Shared types for the sketchbook pipeline engine."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


class Image:
    """Wraps a numpy array representing an image."""

    def __init__(self, data: np.ndarray) -> None:
        self.data = data

    @classmethod
    def load(cls, path: str | Path) -> Image:
        """Load an image from disk."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        data = cv2.imread(str(path))
        if data is None:
            raise ValueError(f"Could not decode image: {path}")
        return cls(data)

    def save(self, path: str | Path) -> None:
        """Write the image to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), self.data)
