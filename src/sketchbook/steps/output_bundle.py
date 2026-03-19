"""OutputBundle step — marks a node for inclusion in a named output bundle."""

from __future__ import annotations

from typing import Any

from sketchbook.core.step import PipelineStep


class OutputBundle(PipelineStep):
    """Passthrough step that marks a node as an output for a named bundle.

    The builder scans for OutputBundle nodes matching the requested bundle_name,
    iterates saved presets, and bakes variant images into the output directory.
    The bundle JSON is written to <output_dir>/<bundle_name>.json.
    """

    def __init__(self, bundle_name: str) -> None:
        self.bundle_name = bundle_name
        super().__init__()

    def setup(self) -> None:
        """Declare a single image input."""
        self.add_input("image", type=object)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Any:
        """Pass the input image through unchanged."""
        return inputs["image"]
