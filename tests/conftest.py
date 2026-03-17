"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sketchbook.core.executor import execute
from sketchbook.server.app import create_app


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def make_test_image(path: Path, color: str = "blue") -> None:
    """Write a small solid-color JPEG to path."""
    import cv2

    colors = {
        "blue": (255, 0, 0),
        "red": (0, 0, 255),
        "green": (0, 255, 0),
        "white": (255, 255, 255),
    }
    bgr = colors.get(color, (128, 128, 128))
    img = np.full((64, 64, 3), bgr, dtype=np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def write_test_image(path: Path, color: str = "red") -> None:
    """Overwrite an existing test image with a new color (used in watcher tests)."""
    make_test_image(path, color)


# ---------------------------------------------------------------------------
# tmp_sketch fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_sketch(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary sketch directory with a test source image."""
    sketch_dir = tmp_path / "hello"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "fence-torn-paper.png")
    yield sketch_dir


# ---------------------------------------------------------------------------
# test_client fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_client(tmp_sketch: Path) -> Generator[TestClient, None, None]:
    """Build the Hello sketch and return a FastAPI TestClient."""
    from sketches.hello import Hello

    sketch = Hello(tmp_sketch)
    execute(sketch.dag)

    app = create_app({"hello": sketch}, sketches_dir=tmp_sketch.parent)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# ws_client fixture (async context manager factory)
# ---------------------------------------------------------------------------

@pytest.fixture()
def ws_client(test_client: TestClient):
    """Return a factory that opens a WebSocket connection via the TestClient."""
    def _factory(path: str):
        return test_client.websocket_connect(path)
    return _factory


# ---------------------------------------------------------------------------
# edge_hello fixtures (increment 2)
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_edge_sketch(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary sketch directory for EdgeHello with a test source image."""
    sketch_dir = tmp_path / "edge_hello"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "hello.jpg")
    yield sketch_dir


@pytest.fixture()
def edge_test_client(tmp_edge_sketch: Path) -> Generator[TestClient, None, None]:
    """Build the EdgeHello sketch and return a FastAPI TestClient."""
    from sketches.edge_hello import EdgeHello

    sketch = EdgeHello(tmp_edge_sketch)
    execute(sketch.dag)

    app = create_app({"edge_hello": sketch}, sketches_dir=tmp_edge_sketch.parent)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest.fixture()
def edge_ws_client(edge_test_client: TestClient):
    """Return a factory that opens a WebSocket connection via the edge TestClient."""
    def _factory(path: str):
        return edge_test_client.websocket_connect(path)
    return _factory
