"""Acceptance tests for Increment 6: Sketch Browser and Multi-Sketch Discovery."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sketchbook import Sketch
from sketchbook.server.app import create_app
from tests.steps import EdgeDetect, GaussianBlur, Passthrough

# ---------------------------------------------------------------------------
# Test sketch definitions
# ---------------------------------------------------------------------------


class _BrowserHelloSketch(Sketch):
    """Minimal sketch for the browser acceptance test."""

    name = "Hello"
    description = "Simplest possible sketch."
    date = "2026-03-16"

    def build(self) -> None:
        """Wire source through passthrough."""
        photo = self.source("photo", "assets/hello.jpg")
        photo.pipe(Passthrough)


class _BrowserEdgePortraitSketch(Sketch):
    """Edge detection sketch for the browser acceptance test."""

    name = "Edge Portrait"
    description = "Canny edge detection."
    date = "2026-03-18"

    def build(self) -> None:
        """Wire source through blur then edge detect."""
        photo = self.source("photo", "assets/photo.jpg")
        photo.pipe(GaussianBlur).pipe(EdgeDetect)


def _make_image(path: Path) -> None:
    import cv2

    img = np.zeros((64, 64, 3), dtype=np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def two_sketches_client(tmp_path: Path) -> Generator[TestClient]:
    """Return a TestClient with two sketch candidates (neither pre-loaded)."""
    _make_image(tmp_path / "hello" / "assets" / "hello.jpg")
    _make_image(tmp_path / "edge_portrait" / "assets" / "photo.jpg")

    app = create_app(
        {},
        sketches_dir=tmp_path,
        candidates={
            "hello": _BrowserHelloSketch,
            "edge_portrait": _BrowserEdgePortraitSketch,
        },
    )
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_index_lists_all_sketches(two_sketches_client: TestClient) -> None:
    """The index page lists all discovered sketches."""
    response = two_sketches_client.get("/")
    assert response.status_code == 200
    assert "Edge Portrait" in response.text
    assert "Hello" in response.text


def test_index_links_to_sketch_pages(two_sketches_client: TestClient) -> None:
    """The index page contains links to each sketch's overview page."""
    response = two_sketches_client.get("/")
    assert "/sketch/hello" in response.text
    assert "/sketch/edge_portrait" in response.text


def test_only_active_sketch_watches_files(two_sketches_client: TestClient) -> None:
    """Navigating to a sketch activates its watchers; unvisited sketches stay unwatched."""
    registry = two_sketches_client.app.state.registry

    # Neither sketch has been accessed yet
    assert "edge_portrait" not in registry.get_watched_sketch_ids()
    assert "hello" not in registry.get_watched_sketch_ids()

    # Navigate to edge_portrait — triggers lazy load and watcher registration
    two_sketches_client.get("/sketch/edge_portrait")

    assert "edge_portrait" in registry.get_watched_sketch_ids()
    assert "hello" not in registry.get_watched_sketch_ids()
