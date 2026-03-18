"""TwoChains — two fully disconnected subgraphs in one sketch."""

from sketchbook import Sketch
from sketchbook.steps.opencv.blur import GaussianBlur
from sketchbook.steps.opencv.edge_detect import EdgeDetect


class TwoChains(Sketch):
    """Two independent source → process chains with no shared nodes.

    Exercises a topo sort with two connected components (two root nodes),
    verifying both chains execute and appear in the rendered feed.
    """

    name = "Two Chains"
    description = "Two separate blur-to-edge pipelines running side by side."
    date = "2026-03-18"

    def build(self) -> None:
        """Wire two independent source → blur → edge chains."""
        photo_a = self.source("photo_a", "assets/photo_a.jpg")
        photo_a.pipe(GaussianBlur).pipe(EdgeDetect)

        photo_b = self.source("photo_b", "assets/photo_b.jpg")
        photo_b.pipe(EdgeDetect)
