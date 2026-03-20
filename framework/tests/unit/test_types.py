"""Unit tests for Image: load, save, round-trip integrity."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sketchbook.core.types import Image

# ---------------------------------------------------------------------------
# Image.load
# ---------------------------------------------------------------------------

def test_load_valid_image(tmp_path: Path) -> None:
    import cv2

    img_path = tmp_path / "test.png"
    data = np.full((16, 16, 3), 128, dtype=np.uint8)
    cv2.imwrite(str(img_path), data)

    img = Image.load(img_path)
    assert isinstance(img, Image)
    assert img.data.shape == (16, 16, 3)


def test_load_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError, match="Image not found"):
        Image.load("/nonexistent/path/image.png")


def test_load_invalid_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "not_an_image.png"
    bad.write_bytes(b"not image data")
    with pytest.raises(ValueError, match="Could not decode image"):
        Image.load(bad)


def test_load_accepts_string_path(tmp_path: Path) -> None:
    import cv2

    img_path = tmp_path / "test.png"
    cv2.imwrite(str(img_path), np.zeros((4, 4, 3), dtype=np.uint8))
    img = Image.load(str(img_path))
    assert isinstance(img, Image)


# ---------------------------------------------------------------------------
# Image.save
# ---------------------------------------------------------------------------

def test_save_writes_file(tmp_path: Path) -> None:
    img = Image(np.zeros((8, 8, 3), dtype=np.uint8))
    out = tmp_path / "out.png"
    img.save(out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_save_creates_parent_dirs(tmp_path: Path) -> None:
    img = Image(np.zeros((4, 4, 3), dtype=np.uint8))
    out = tmp_path / "nested" / "dir" / "out.png"
    img.save(out)
    assert out.exists()


def test_save_accepts_string_path(tmp_path: Path) -> None:
    img = Image(np.zeros((4, 4, 3), dtype=np.uint8))
    out = tmp_path / "out.png"
    img.save(str(out))
    assert out.exists()


# ---------------------------------------------------------------------------
# Round-trip integrity
# ---------------------------------------------------------------------------

def test_round_trip_preserves_pixel_values(tmp_path: Path) -> None:
    data = np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8)
    img = Image(data)
    out = tmp_path / "round_trip.png"
    img.save(out)

    loaded = Image.load(out)
    np.testing.assert_array_equal(loaded.data, data)


def test_round_trip_preserves_shape(tmp_path: Path) -> None:
    data = np.zeros((32, 64, 3), dtype=np.uint8)
    img = Image(data)
    out = tmp_path / "shape.png"
    img.save(out)

    loaded = Image.load(out)
    assert loaded.data.shape == (32, 64, 3)
