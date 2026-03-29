"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from sketchbook import Sketch
from sketchbook.core.executor import execute
from sketchbook.core.types import Image
from sketchbook.server.app import create_app
from tests.steps import EdgeDetect, GaussianBlur, Passthrough


def _cv2_loader(path: Path) -> Image:
    """Load an image using cv2 — for use in test fixture sketches."""
    return Image(cv2.imread(str(path)))

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
def tmp_sketch(tmp_path: Path) -> Generator[Path]:
    """Create a temporary sketch directory with a test source image."""
    sketch_dir = tmp_path / "hello"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "fence-torn-paper.png")
    yield sketch_dir


# ---------------------------------------------------------------------------
# test_client fixture
# ---------------------------------------------------------------------------

class _HelloSketch(Sketch):
    """Minimal inline sketch for walking skeleton acceptance tests."""

    name = "Hello"
    description = "Simplest possible sketch."
    date = "2026-03-16"

    def build(self) -> None:
        """Wire a source image through a passthrough step."""
        photo = self.source("photo", "assets/fence-torn-paper.png", loader=_cv2_loader)
        photo.pipe(Passthrough)


@pytest.fixture()
def test_client(tmp_sketch: Path) -> Generator[TestClient]:
    """Build the Hello sketch and return a FastAPI TestClient."""
    sketch = _HelloSketch(tmp_sketch)
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
def tmp_edge_sketch(tmp_path: Path) -> Generator[Path]:
    """Create a temporary sketch directory for EdgeHello with a test source image."""
    sketch_dir = tmp_path / "edge_hello"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "hello.jpg")
    yield sketch_dir


class _EdgeHelloSketch(Sketch):
    """Minimal inline sketch for edge detection acceptance tests."""

    name = "Edge Hello"
    description = "Canny edge detection with tunable thresholds."
    date = "2026-03-16"

    def build(self) -> None:
        """Wire a source image through blur then edge detection."""
        photo = self.source("photo", "assets/hello.jpg", loader=_cv2_loader)
        photo.pipe(GaussianBlur, params={"sigma": {"max": 3.0, "step": 0.05}}).pipe(EdgeDetect)


@pytest.fixture()
def edge_test_client(tmp_edge_sketch: Path) -> Generator[TestClient]:
    """Build the EdgeHello sketch and return a FastAPI TestClient."""
    sketch = _EdgeHelloSketch(tmp_edge_sketch)
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


# ---------------------------------------------------------------------------
# multi-step pipeline fixtures (increment 4)
# ---------------------------------------------------------------------------


class _MultiStepSketch(Sketch):
    """Inline sketch with source → blur → edge detect for DAG/params endpoint tests."""

    name = "Multi Step"
    description = "source → blur → edge detect"
    date = "2026-03-18"

    def build(self) -> None:
        """Wire photo through blur then edge detection."""
        photo = self.source("photo", "assets/photo.jpg", loader=_cv2_loader)
        photo.pipe(GaussianBlur).pipe(EdgeDetect)


@pytest.fixture()
def tmp_multi_step_sketch(tmp_path: Path) -> Generator[Path]:
    """Create a temporary sketch directory for the multi-step pipeline tests."""
    sketch_dir = tmp_path / "multi_step"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "photo.jpg")
    yield sketch_dir


@pytest.fixture()
def multi_step_client(tmp_multi_step_sketch: Path) -> Generator[TestClient]:
    """Build the multi-step sketch and return a FastAPI TestClient."""
    sketch = _MultiStepSketch(tmp_multi_step_sketch)
    execute(sketch.dag)

    app = create_app({"multi_step": sketch}, sketches_dir=tmp_multi_step_sketch.parent)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# masked edge sketch fixtures (increment 5)
# ---------------------------------------------------------------------------


class _MaskedEdgeSketch(Sketch):
    """Sketch with source_photo → blur → edge_detect(mask=source_mask)."""

    name = "Edge Portrait"
    description = "Multi-source: blur + optional mask into edge detect."
    date = "2026-03-18"

    def build(self) -> None:
        """Wire photo through blur, with mask as optional second input to edge detect."""
        photo = self.source("photo", "assets/photo.jpg", loader=_cv2_loader)
        mask = self.source("mask", "assets/mask.png", loader=_cv2_loader)
        blur = photo.pipe(GaussianBlur)
        self.add(EdgeDetect, inputs={"image": blur, "mask": mask})


class _NoMaskEdgeSketch(Sketch):
    """Same pipeline as _MaskedEdgeSketch but without the mask input connected."""

    name = "Edge Portrait No Mask"
    description = "Optional mask input not wired."
    date = "2026-03-18"

    def build(self) -> None:
        """Wire photo through blur then edge detect (no mask)."""
        photo = self.source("photo", "assets/photo.jpg", loader=_cv2_loader)
        blur = photo.pipe(GaussianBlur)
        blur.pipe(EdgeDetect)


@pytest.fixture()
def tmp_masked_sketch(tmp_path: Path) -> Generator[Path]:
    """Create a sketch directory with both photo and mask assets."""
    sketch_dir = tmp_path / "edge_portrait"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "photo.jpg")
    make_test_image(assets_dir / "mask.png", color="white")
    yield sketch_dir


@pytest.fixture()
def masked_client(tmp_masked_sketch: Path) -> Generator[TestClient]:
    """Build the masked edge sketch and return a FastAPI TestClient."""
    sketch = _MaskedEdgeSketch(tmp_masked_sketch)
    execute(sketch.dag)

    app = create_app({"edge_portrait": sketch}, sketches_dir=tmp_masked_sketch.parent)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest.fixture()
def masked_ws_client(masked_client: TestClient):
    """Return a factory that opens a WebSocket connection via the masked client."""
    def _factory(path: str):
        return masked_client.websocket_connect(path)
    return _factory


@pytest.fixture()
def tmp_no_mask_sketch(tmp_path: Path) -> Generator[Path]:
    """Create a sketch directory with only a photo asset (no mask)."""
    sketch_dir = tmp_path / "edge_portrait_no_mask"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "photo.jpg")
    yield sketch_dir


@pytest.fixture()
def no_mask_client(tmp_no_mask_sketch: Path) -> Generator[TestClient]:
    """Build the no-mask edge sketch and return a FastAPI TestClient."""
    sketch = _NoMaskEdgeSketch(tmp_no_mask_sketch)
    execute(sketch.dag)

    app = create_app({"edge_portrait_no_mask": sketch}, sketches_dir=tmp_no_mask_sketch.parent)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client
