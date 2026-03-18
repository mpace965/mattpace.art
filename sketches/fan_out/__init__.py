"""FanOut — one source feeds three independent branches."""

from sketchbook import Sketch
from sketchbook.steps import Passthrough
from sketchbook.steps.opencv.blur import GaussianBlur
from sketchbook.steps.opencv.edge_detect import EdgeDetect


class FanOut(Sketch):
    """Fan-out from a single source node to three parallel branches.

    Exercises a source node referenced as input by multiple downstream nodes
    and a topo sort that must place source unambiguously first.
    """

    name = "Fan Out"
    description = "One source image processed three ways simultaneously."
    date = "2026-03-18"

    def build(self) -> None:
        """Wire source into blur, edge detection, and passthrough in parallel."""
        photo = self.source("photo", "assets/photo.jpg")
        photo.pipe(GaussianBlur)
        photo.pipe(EdgeDetect)
        photo.pipe(Passthrough)
