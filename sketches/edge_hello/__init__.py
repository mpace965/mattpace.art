"""EdgeHello — minimal edge detection sketch for testing."""

from sketchbook import Sketch
from sketchbook.steps.opencv.blur import GaussianBlur
from sketchbook.steps.opencv.edge_detect import EdgeDetect


class EdgeHello(Sketch):
    site_presets = ["region_edge"]

    """Edge detection sketch used in increment 2 acceptance tests."""

    name = "Edge Hello"
    description = "Canny edge detection with tunable thresholds."
    date = "2026-03-16"

    def build(self) -> None:
        """Wire a source image through blur then edge detection."""
        photo = self.source("photo", "assets/hello.jpg")
        edges = photo.pipe(GaussianBlur, params={"sigma": {"max": 3.0, "step": 0.05}}).pipe(EdgeDetect)
        self.site_output(edges)
