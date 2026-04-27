"""Shore tessellation — identity/inverse grid tessellation over a two-tone landscape."""

from __future__ import annotations

from typing import Annotated, Any, Literal

import cv2
import numpy as np
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, SketchContext, sketch, step

from sketches import SITE_BUNDLE
from sketches.types import Image


@sketch(date="2026-04-17")
def shore_tessellation() -> None:
    """truchet tiles from a rocky shore and the sea and sky."""
    photo = source("assets/shore.png", Image.load)
    scale = downscale_factor()
    image = downscale(photo, scale)
    blurred = blur(image)
    mask = segment(blurred)
    mask_preview(mask)
    result = render(image, mask)
    output(result, SITE_BUNDLE)


@step
def downscale_factor(ctx: SketchContext) -> float:
    return 0.25 if ctx.mode == "dev" else 0.75


@step
def downscale(image: Image, scale: float) -> Image:
    """Return the image scaled by scale using area interpolation."""
    src = image.array
    h, w = src.shape[:2]
    return Image(
        cv2.resize(
            src,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    )


@step
def blur(
    image: Image,
    *,
    radius: Annotated[int, Param(min=0, max=200, step=1, debounce=150)] = 10,
) -> Image:
    """Return the image blurred with a Gaussian kernel of the given radius."""
    if radius == 0:
        return image
    k = radius * 2 + 1
    return Image(cv2.GaussianBlur(image.array, (k, k), 0))


@step
def segment(image: Image) -> Image:
    """Return a binary mask via k-means (k=2) on LAB: 0=dark/rocky, 1=bright/sky."""
    src = image.array
    lab = cv2.cvtColor(src, cv2.COLOR_BGR2LAB)
    pixels = lab.reshape(-1, 3)[:, 1:].astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(pixels, 2, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    labels = labels.reshape(src.shape[:2]).astype(np.uint8)
    # Guarantee label 0 = darker cluster (rocky), 1 = brighter cluster (sky).
    # Use mean L from the original LAB image since centers no longer carry L.
    l_channel = lab[:, :, 0].astype(np.float32)
    mean_l_0 = l_channel[labels == 0].mean()
    mean_l_1 = l_channel[labels == 1].mean()
    if mean_l_0 > mean_l_1:
        labels = 1 - labels
    return Image(labels)


@step
def mask_preview(mask: Image) -> Image:
    """Return the binary mask scaled to [0, 255] for inspection."""
    return Image(mask.array * 255)


TileVariant = tuple[Literal["/", "\\"], bool]
TileStrategy = Any  # (rng, row, col, grid_size) -> TileVariant


def _checkerboard_strategy(rng: Any, row: int, col: int, n: int) -> TileVariant:
    """Return the tile variant that places minority corners at alternating intersections."""
    match (row % 2, col % 2):
        case (0, 0):
            return ("/", True)
        case (0, 1):
            return ("\\", True)
        case (1, 0):
            return ("\\", False)
        case (1, 1):
            return ("/", False)


_TILE_STRATEGIES: dict[str, TileStrategy] = {
    "random": lambda rng, row, col, n: (
        ("/", "\\")[rng.integers(2)],
        bool(rng.integers(2)),
    ),
    "triangles": lambda rng, row, col, n: (("/", "\\")[(row + col) % 2], False),
    "checkerboard": _checkerboard_strategy,
    "row_chevrons": lambda rng, row, col, n: ("/" if col % 2 == 0 else "\\", row % 2 == 0),
}
_TILE_STRATEGY_OPTIONS = list(_TILE_STRATEGIES.keys())


def _make_tile(
    patch_a: np.ndarray,
    patch_b: np.ndarray,
    orientation: Literal["/", "\\"],
    invert: bool,
    size: int,
) -> np.ndarray:
    """Return a size×size truchet tile, patch_a in the primary region unless inverted."""
    ys, xs = np.indices((size, size))
    # /: primary = upper-left triangle; \: primary = upper-right triangle
    primary = (ys + xs) < size if orientation == "/" else ys < xs
    if invert:
        primary = ~primary
    return np.where(primary[:, :, np.newaxis], patch_a, patch_b)


@step
def render(
    image: Image,
    mask: Image,
    *,
    seed: Annotated[int, Param(min=0, max=9999, step=1)] = 42,
    grid_size: Annotated[int, Param(min=1, max=32, step=1)] = 10,
    tile_size: Annotated[float, Param(min=0.01, max=1.0, step=0.01, debounce=150)] = 0.1,
    tile_strategy: Annotated[str, Param(options=_TILE_STRATEGY_OPTIONS)] = "random",
) -> Image:
    """Return a grid_size×grid_size grid of truchet tiles using the selected strategy."""
    src = image.array
    m = mask.array
    h, w = src.shape[:2]
    size = max(1, int(min(h, w) * tile_size))
    strategy = _TILE_STRATEGIES[tile_strategy]

    strategy_rng = np.random.default_rng(seed)
    donor_rng = np.random.default_rng(seed ^ 0xABCD)

    def _pick(label: int) -> np.ndarray:
        """Sample a tile-sized crop dominated by label (0=A, 1=B) using normalized coords."""
        threshold = 0.2 if label == 0 else 0.8
        for _ in range(64):
            sy = int(donor_rng.random() * (h - size))
            sx = int(donor_rng.random() * (w - size))
            frac = m[sy : sy + size, sx : sx + size].mean()
            if (label == 0 and frac < threshold) or (label == 1 and frac > threshold):
                return src[sy : sy + size, sx : sx + size].copy()
        return np.zeros((size, size, src.shape[2]), dtype=src.dtype)

    rows = []
    for row in range(grid_size):
        row_tiles = []
        for col in range(grid_size):
            orientation, invert = strategy(strategy_rng, row, col, grid_size)
            row_tiles.append(_make_tile(_pick(0), _pick(1), orientation, invert, size))
        rows.append(np.concatenate(row_tiles, axis=1))
    return Image(np.concatenate(rows, axis=0).astype(src.dtype))
