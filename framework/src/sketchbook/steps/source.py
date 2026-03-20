"""SourceFile step — reads an image from disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image


class SourceFile(PipelineStep):
    """Reads a single image file from disk and passes it downstream."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        super().__init__()

    def setup(self) -> None:
        """No inputs — this is a source node."""

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Load and return the image from disk."""
        return Image.load(self._path)
