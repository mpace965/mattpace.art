"""Unit tests for lazy watcher activation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from sketchbook import Sketch
from sketchbook.core.executor import execute
from sketchbook.server.registry import SketchRegistry
from tests.steps import EdgeDetect, GaussianBlur, Passthrough


class _SingleSourceSketch(Sketch):
    """One source + one passthrough — only one SourceFile node to watch."""

    name = "Single Source"
    description = "single source watcher test"
    date = "2026-03-18"

    def build(self) -> None:
        photo = self.source("photo", "assets/test.jpg")
        photo.pipe(Passthrough)


class _TwoSourceSketch(Sketch):
    """Two sources — two SourceFile nodes to watch."""

    name = "Two Sources"
    description = "two source watcher test"
    date = "2026-03-18"

    def build(self) -> None:
        photo = self.source("photo", "assets/photo.jpg")
        mask = self.source("mask", "assets/mask.jpg")
        blur = photo.pipe(GaussianBlur)
        self.add(EdgeDetect, inputs={"image": blur, "mask": mask})


def _make_image(path: Path) -> None:
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def _make_registry_with_watcher(mock_watcher, mock_loop) -> SketchRegistry:
    """Return a SketchRegistry with mock watcher/loop already injected."""
    registry = SketchRegistry({}, None)
    registry._watcher = mock_watcher
    registry._loop = mock_loop
    return registry


def test_register_watch_calls_watch_once_for_single_source(tmp_path: Path) -> None:
    """_register_watch calls watcher.watch exactly once for a sketch with one source."""
    sketch_dir = tmp_path / "single"
    _make_image(sketch_dir / "assets" / "test.jpg")

    sketch = _SingleSourceSketch(sketch_dir)
    execute(sketch.dag)

    mock_watcher = MagicMock()
    mock_loop = MagicMock()
    registry = _make_registry_with_watcher(mock_watcher, mock_loop)
    registry._register_watch("single", sketch)

    assert mock_watcher.watch.call_count == 1


def test_register_watch_watches_correct_path(tmp_path: Path) -> None:
    """_register_watch passes the source file path to watcher.watch."""
    sketch_dir = tmp_path / "single"
    source_path = sketch_dir / "assets" / "test.jpg"
    _make_image(source_path)

    sketch = _SingleSourceSketch(sketch_dir)
    execute(sketch.dag)

    mock_watcher = MagicMock()
    mock_loop = MagicMock()
    registry = _make_registry_with_watcher(mock_watcher, mock_loop)
    registry._register_watch("single", sketch)

    watched_path = mock_watcher.watch.call_args[0][0]
    assert Path(watched_path) == source_path


def test_register_watch_calls_watch_for_each_source(tmp_path: Path) -> None:
    """_register_watch calls watcher.watch once per SourceFile node."""
    sketch_dir = tmp_path / "two"
    _make_image(sketch_dir / "assets" / "photo.jpg")
    _make_image(sketch_dir / "assets" / "mask.jpg")

    sketch = _TwoSourceSketch(sketch_dir)
    execute(sketch.dag)

    mock_watcher = MagicMock()
    mock_loop = MagicMock()
    registry = _make_registry_with_watcher(mock_watcher, mock_loop)
    registry._register_watch("two", sketch)

    assert mock_watcher.watch.call_count == 2


def test_register_watch_does_not_watch_non_source_nodes(tmp_path: Path) -> None:
    """_register_watch ignores non-SourceFile nodes (e.g. Passthrough)."""
    sketch_dir = tmp_path / "single"
    _make_image(sketch_dir / "assets" / "test.jpg")

    sketch = _SingleSourceSketch(sketch_dir)
    execute(sketch.dag)

    # pipeline has 2 nodes: SourceFile + Passthrough — only source should be watched
    node_count = len(sketch.dag.topo_sort())
    assert node_count == 2

    mock_watcher = MagicMock()
    mock_loop = MagicMock()
    registry = _make_registry_with_watcher(mock_watcher, mock_loop)
    registry._register_watch("single", sketch)

    # Only 1 watch call, not 2
    assert mock_watcher.watch.call_count == 1
