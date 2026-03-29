"""Unit tests for PipelineValue, Image: interface, construction, serialisation."""

from __future__ import annotations

import numpy as np

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
