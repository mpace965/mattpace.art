"""Diamond — fan-out then fan-in on the same ancestor."""

from sketchbook import Sketch
from sketchbook.steps.opencv.blend import Blend
from sketchbook.steps.opencv.blur import GaussianBlur
from sketchbook.steps.opencv.edge_detect import EdgeDetect


class Diamond(Sketch):
    """Diamond DAG: source → blur → [edge_1, edge_2] → blend.

    Exercises a shared intermediate node (blur) consumed by two downstream
    steps and verifies that blur's output is reused rather than recomputed.
    Both edge variants feed into a final blend, creating the classic diamond.
    """

    name = "Diamond"
    description = "Two edge passes on a shared blur, blended back together."
    date = "2026-03-18"

    def build(self) -> None:
        """Fork after blur into two edge detections and recombine with blend."""
        photo = self.source("photo", "assets/photo.jpg")
        blurred = photo.pipe(GaussianBlur)
        tight = blurred.pipe(
            EdgeDetect,
            params={"low_threshold": {"default": 50.0}, "high_threshold": {"default": 100.0}},
        )
        loose = blurred.pipe(
            EdgeDetect,
            params={"low_threshold": {"default": 150.0}, "high_threshold": {"default": 300.0}},
        )
        self.add(Blend, inputs={"image": tight, "overlay": loose})
