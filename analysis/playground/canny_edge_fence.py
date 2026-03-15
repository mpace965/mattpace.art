"""
Interactive Canny edge detection playground for fence-torn-paper sketch.
Uses Panel + param for reactive parameter tuning.

Usage:
    uv run python playground/canny_edge_fence.py
"""

import cv2
import numpy as np
import param
import panel as pn
from PIL import Image

from sketchbook.paths import find_image

pn.extension()

SKETCH = "fence-torn-paper"
IMAGE_STEM = "fence-torn-paper"

src = find_image(SKETCH, IMAGE_STEM)
_img_bgr = cv2.imread(str(src))
_img_rgb = cv2.cvtColor(_img_bgr, cv2.COLOR_BGR2RGB)
_gray = cv2.cvtColor(_img_bgr, cv2.COLOR_BGR2GRAY)


class CannyExplorer(param.Parameterized):
    blur  = param.Integer(5,   bounds=(1, 21),  step=2)
    low   = param.Integer(50,  bounds=(0, 255), step=1)
    high  = param.Integer(150, bounds=(0, 255), step=1)

    @param.depends("blur", "low", "high")
    def view(self):
        k = self.blur | 1
        blurred = cv2.GaussianBlur(_gray, (k, k), 0)
        edges = cv2.Canny(blurred, self.low, self.high)

        original = pn.pane.PNG(Image.fromarray(_img_rgb), sizing_mode="scale_both")
        edge_img = pn.pane.PNG(Image.fromarray(edges),   sizing_mode="scale_both", styles={"filter": "invert(1)"})

        return pn.Row(original, edge_img, sizing_mode="stretch_width")


explorer = CannyExplorer()

app = pn.Column(
    explorer.param.blur,
    explorer.param.low,
    explorer.param.high,
    explorer.view,
    sizing_mode="stretch_width",
)

pn.serve(app, show=True)
