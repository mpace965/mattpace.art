"""Unit tests for SourceFile: path storage, loader delegation, error on missing loader."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from sketchbook.core.types import Image
from sketchbook.steps.source import SourceFile


def _dummy_loader(path: Path) -> Image:
    """Return a blank image regardless of path."""
    return Image(np.zeros((4, 4, 3), dtype=np.uint8))


def test_source_file_stores_path(tmp_path: Path) -> None:
    """SourceFile remembers the path it was given."""
    p = tmp_path / "photo.png"
    step = SourceFile(p)
    assert step._path == p


def test_source_file_without_loader_raises_on_process(tmp_path: Path) -> None:
    """Calling process() without a loader raises ValueError with a helpful message."""
    step = SourceFile(tmp_path / "photo.png")
    step.setup()
    with pytest.raises(ValueError, match="loader"):
        step.process({}, {})


def test_source_file_process_calls_loader_with_path(tmp_path: Path) -> None:
    """process() passes the stored path to the loader."""
    called_with: list[Path] = []

    def recording_loader(p: Path) -> Image:
        called_with.append(p)
        return Image(np.zeros((4, 4, 3), dtype=np.uint8))

    p = tmp_path / "photo.png"
    step = SourceFile(p, loader=recording_loader)
    step.setup()
    step.process({}, {})

    assert called_with == [p]


def test_source_file_process_returns_loader_result(tmp_path: Path) -> None:
    """process() returns whatever the loader returns."""
    expected = Image(np.full((2, 2, 3), 42, dtype=np.uint8))
    step = SourceFile(tmp_path / "photo.png", loader=lambda _: expected)
    step.setup()
    result = step.process({}, {})
    assert result is expected
