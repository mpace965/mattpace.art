"""Acceptance test 08: loader decoupling.

Acceptance criteria:
    Image is a PipelineValue with extension and mime_type.
    Image.to_bytes() produces valid PNG bytes without cv2.
    Image has no load or save methods.
    A sketch that passes a loader= to source() runs end-to-end and the result
    is visible in the browser — identical to the walking skeleton, but image
    loading is entirely the sketch's responsibility and the workdir write
    goes through to_bytes(), not cv2.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from sketchbook import Sketch
from sketchbook.core.executor import execute
from sketchbook.core.profile import ExecutionProfile
from sketchbook.core.types import Image
from sketchbook.server.app import create_app
from tests.conftest import make_test_image
from tests.steps import Passthrough


def test_image_is_pipeline_value() -> None:
    """Image must subclass PipelineValue."""
    from sketchbook.core.types import PipelineValue
    assert issubclass(Image, PipelineValue)


def test_image_extension_is_png() -> None:
    assert Image.extension == "png"


def test_image_mime_type_is_image_png() -> None:
    assert Image.mime_type == "image/png"


def test_image_to_bytes_produces_valid_png() -> None:
    """to_bytes() returns bytes that start with the PNG magic number."""
    img = Image(np.zeros((8, 8, 3), dtype=np.uint8))
    data = img.to_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_image_has_no_load_method() -> None:
    """Image must not expose a load classmethod — I/O belongs in userland."""
    assert not hasattr(Image, "load"), "Image.load must not exist on the framework type"


def test_image_has_no_save_method() -> None:
    """Image must not expose a save method — I/O belongs in userland."""
    assert not hasattr(Image, "save"), "Image.save must not exist on the framework type"


class _LoaderSketch(Sketch):
    """Sketch that supplies its own cv2-based loader via source(loader=...)."""

    name = "Loader Sketch"
    description = "Tests that a sketch-supplied loader runs end-to-end."
    date = "2026-03-22"

    def build(self, profile: ExecutionProfile) -> None:
        photo = self.source("photo", "assets/photo.png", loader=lambda p: Image(cv2.imread(str(p))))
        photo.pipe(Passthrough)


def test_sketch_with_loader_runs_end_to_end(tmp_path: Path) -> None:
    """A sketch with _source_loader completes pipeline execution without error."""
    sketch_dir = tmp_path / "loader_sketch"
    make_test_image(sketch_dir / "assets" / "photo.png")

    sketch = _LoaderSketch(sketch_dir)
    execute(sketch.dag)  # must not raise


def test_workdir_file_written_via_to_bytes(tmp_path: Path) -> None:
    """After execution the workdir PNG exists and contains valid PNG bytes."""
    sketch_dir = tmp_path / "loader_sketch"
    make_test_image(sketch_dir / "assets" / "photo.png")

    sketch = _LoaderSketch(sketch_dir)
    execute(sketch.dag)

    workdir_files = list((sketch_dir / ".workdir").glob("*.png"))
    assert workdir_files, "No PNG written to workdir"
    assert workdir_files[0].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_sketch_with_loader_result_visible_in_browser(tmp_path: Path) -> None:
    """The server returns an <img> tag for a sketch that uses _source_loader."""
    sketch_dir = tmp_path / "loader_sketch"
    make_test_image(sketch_dir / "assets" / "photo.png")

    sketch = _LoaderSketch(sketch_dir)
    execute(sketch.dag)

    app = create_app({"loader_sketch": sketch}, sketches_dir=tmp_path)
    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.get("/sketch/loader_sketch/step/passthrough_0")
        assert response.status_code == 200
        assert "<img" in response.text
