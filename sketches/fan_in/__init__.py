"""FanIn — two sources merged by a multi-input blend step."""

from sketchbook import Sketch
from sketchbook.steps.opencv.blend import Blend
from sketchbook.steps.opencv.blur import GaussianBlur


class FanIn(Sketch):
    """Fan-in from two independent source nodes into a single blend step.

    Exercises Sketch.add() with a multi-key inputs dict and the executor
    resolving both named inputs before calling process().
    """

    name = "Fan In"
    description = "Two blurred sources combined into a weighted blend."
    date = "2026-03-18"

    def build(self) -> None:
        """Blur two sources independently then blend them together."""
        photo_a = self.source("photo_a", "assets/photo_a.jpg")
        photo_b = self.source("photo_b", "assets/photo_b.jpg")
        blurred_a = photo_a.pipe(GaussianBlur)
        blurred_b = photo_b.pipe(GaussianBlur)
        self.add(Blend, inputs={"image": blurred_a, "overlay": blurred_b})
