"""Unit tests for PipelineValue, Image: interface, construction, serialisation."""

from __future__ import annotations

import io as _io

import numpy as np
from PIL import Image as PILImage

from sketchbook.core.types import Image, PipelineValue

# ---------------------------------------------------------------------------
# PipelineValue interface on Image
# ---------------------------------------------------------------------------

def test_image_is_pipeline_value() -> None:
    assert issubclass(Image, PipelineValue)


def test_image_extension() -> None:
    assert Image.extension == "png"


def test_image_mime_type() -> None:
    assert Image.mime_type == "image/png"


def test_image_to_bytes_returns_png_magic() -> None:
    img = Image(np.zeros((8, 8, 3), dtype=np.uint8))
    assert img.to_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_image_to_bytes_non_empty() -> None:
    img = Image(np.full((4, 4, 3), 128, dtype=np.uint8))
    assert len(img.to_bytes()) > 0


# ---------------------------------------------------------------------------
# Image wrapper
# ---------------------------------------------------------------------------

def test_image_stores_ndarray() -> None:
    data = np.zeros((8, 8, 3), dtype=np.uint8)
    img = Image(data)
    assert img.data is data


def test_image_has_no_load_method() -> None:
    assert not hasattr(Image, "load")


def test_image_has_no_save_method() -> None:
    assert not hasattr(Image, "save")


def test_image_data_shape_preserved() -> None:
    data = np.zeros((16, 32, 3), dtype=np.uint8)
    img = Image(data)
    assert img.data.shape == (16, 32, 3)


# ---------------------------------------------------------------------------
# compress_level
# ---------------------------------------------------------------------------

def test_image_compress_level_default_is_zero() -> None:
    img = Image(np.zeros((4, 4, 3), dtype=np.uint8))
    assert img.compress_level == 0


def test_image_compress_level_stored() -> None:
    img = Image(np.zeros((4, 4, 3), dtype=np.uint8), compress_level=9)
    assert img.compress_level == 9


def test_image_to_bytes_uses_compress_level() -> None:
    """compress_level=9 produces fewer bytes than compress_level=0 for compressible data."""
    # Gradient data compresses well; random data does not (deflate can't reduce entropy).
    xs = np.linspace(0, 255, 64, dtype=np.uint8)
    row = np.stack([xs, xs, xs], axis=-1)
    data = np.tile(row, (64, 1, 1))
    small = Image(data, compress_level=9)
    large = Image(data, compress_level=0)
    assert len(small.to_bytes()) < len(large.to_bytes())


def test_image_to_bytes_lossless_at_all_levels() -> None:
    """All compress levels produce identical pixel data on round-trip."""
    rng = np.random.default_rng(7)
    data = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
    for level in (0, 6, 9):
        img = Image(data, compress_level=level)
        rt = np.array(PILImage.open(_io.BytesIO(img.to_bytes())))
        assert np.array_equal(rt, data), f"Round-trip failed at compress_level={level}"
