"""SiteOutput step — marks a node for inclusion in the static site build."""

from __future__ import annotations

from typing import Any

from sketchbook.core.step import PipelineStep


class SiteOutput(PipelineStep):
    """Passthrough step that marks a node as a static site output.

    The site builder scans for SiteOutput nodes and bakes their output
    for each saved preset into the dist/ directory.
    """

    def setup(self) -> None:
        """Declare a single image input."""
        self.add_input("image", type=object)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Any:
        """Pass the input image through unchanged."""
        return inputs["image"]
