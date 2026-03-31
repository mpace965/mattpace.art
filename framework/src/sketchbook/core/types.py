"""Shared types for the sketchbook pipeline engine."""

from __future__ import annotations

import io
from abc import ABC, abstractmethod

import numpy as np
from PIL import Image as PILImage


class PipelineValue(ABC):
    """Abstract base class for values that flow through the pipeline.

    Subclasses declare their serialisation format via class attributes and
    implement to_bytes() to produce the wire representation written to the
    workdir. from_bytes() is reserved for future use (Increment B).
    """

    extension: str
    mime_type: str

    @abstractmethod
    def to_bytes(self) -> bytes:
        """Return the serialised representation of this value."""


class Image(PipelineValue):
    """Wraps a numpy array representing an image."""

    extension = "png"
    mime_type = "image/png"

    def __init__(self, data: np.ndarray) -> None:
        self.data = data

    def to_bytes(self) -> bytes:
        """Encode the image array as PNG bytes using Pillow."""
        pil = PILImage.fromarray(self.data)
        buf = io.BytesIO()
        pil.save(buf, format="PNG", compress_level=0)
        return buf.getvalue()
