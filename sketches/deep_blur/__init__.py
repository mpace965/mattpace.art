"""DeepBlur — deep linear chain with repeated step type."""

from sketchbook import Sketch
from sketchbook.steps.opencv.blur import GaussianBlur
from sketchbook.steps.opencv.edge_detect import EdgeDetect


class DeepBlur(Sketch):
    """Five-node linear chain: source → blur × 3 → edge detect.

    Exercises auto-generated node IDs (gaussian_blur_0, gaussian_blur_1,
    gaussian_blur_2), deep topo sort, and per-step workdir images.
    """

    name = "Deep Blur"
    description = "Three sequential blur passes feeding into edge detection."
    date = "2026-03-18"

    def build(self) -> None:
        """Wire source through three blur stages then edge detection."""
        photo = self.source("photo", "assets/photo.jpg")
        (
            photo
            .pipe(GaussianBlur)
            .pipe(GaussianBlur)
            .pipe(GaussianBlur)
            .pipe(EdgeDetect)
        )
