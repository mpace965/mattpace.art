"""OutputBundle step — marks a node for inclusion in a named output bundle."""

from __future__ import annotations

from typing import Any

from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image


class OutputBundle(PipelineStep):
    """Passthrough step that marks a node as an output for a named bundle.

    The builder scans for OutputBundle nodes matching the requested bundle_name,
    iterates saved presets, and bakes variant images into the output directory.
    The bundle JSON is written to <output_dir>/<bundle_name>.json.
    """

    def __init__(
        self, bundle_name: str, presets: list[str] | None = None, compress_level: int = 0
    ) -> None:
        self.bundle_name = bundle_name
        self.presets = presets  # None = all saved presets
        self.compress_level = compress_level
        super().__init__()

    def setup(self) -> None:
        """Declare a single image input."""
        self.add_input("image", type=object)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Return the input image with the configured compress_level stamped on it."""
        img = inputs["image"]
        return Image(img.data, compress_level=self.compress_level)
