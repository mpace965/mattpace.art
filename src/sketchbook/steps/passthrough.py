"""Passthrough step — returns its input unchanged."""

from __future__ import annotations

from typing import Any

from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image


class Passthrough(PipelineStep):
    """Takes an image input and returns it unchanged."""

    def setup(self) -> None:
        """Declare the single image input."""
        self.add_input("image", Image)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Return the input image unchanged."""
        return inputs["image"]
