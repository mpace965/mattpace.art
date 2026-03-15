"""Canny edge detection pipeline.

Detects edges in sketch images and writes contours as JSON.
Parameters were tuned in playground/canny_edge_fence.py.

Usage:
    uv run analysis run edges <sketch>
    uv run analysis run edges <sketch> --image <stem>
"""

import json

import cv2

from sketchbook.paths import find_image, sketch_assets_dir, sketch_image_paths

PIPELINE_NAME = "edges"
VERSION = 1

# Tuned in playground/canny_edge_fence.py
BLUR = 5
LOW = 50
HIGH = 150


def _process_image(image_path) -> dict:
    img = cv2.imread(str(image_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    k = BLUR | 1
    blurred = cv2.GaussianBlur(gray, (k, k), 0)
    edges = cv2.Canny(blurred, LOW, HIGH)

    raw_contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    h, w = img.shape[:2]
    contours = [
        contour[:, 0, :].tolist()
        for contour in raw_contours
        if len(contour) >= 2
    ]

    return {
        "version": VERSION,
        "width": w,
        "height": h,
        "params": {"blur": BLUR, "low": LOW, "high": HIGH},
        "contours": contours,
    }


def run(sketch_name: str, image_stem: str | None = None) -> None:
    """Read from sketch assets, write edge contours JSON back to sketch assets."""
    if image_stem is not None:
        path = find_image(sketch_name, image_stem)
        if path is None:
            raise FileNotFoundError(
                f"no image with stem '{image_stem}' in sketch '{sketch_name}'"
            )
        paths = [path]
    else:
        paths = sketch_image_paths(sketch_name)
        if not paths:
            raise FileNotFoundError(f"no images found for sketch '{sketch_name}'")

    assets = sketch_assets_dir(sketch_name)

    for path in paths:
        data = _process_image(path)
        out = assets / f"{path.stem}.{PIPELINE_NAME}.json"
        out.write_text(json.dumps(data, separators=(",", ":")))
        print(f"wrote {out.relative_to(assets.parent.parent.parent.parent)}")
