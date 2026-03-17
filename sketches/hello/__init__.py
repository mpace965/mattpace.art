"""Hello — simplest possible sketch."""

from sketchbook import Sketch
from sketchbook.steps import Passthrough


class Hello(Sketch):
    """Simplest possible sketch — one source, one passthrough."""

    name = "Hello"
    description = "Simplest possible sketch."
    date = "2026-03-16"

    def build(self) -> None:
        """Wire a source image through a passthrough step."""
        photo = self.source("photo", "assets/fence-torn-paper.png")
        photo.pipe(Passthrough)
