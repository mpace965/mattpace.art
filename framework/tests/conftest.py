"""Shared pytest fixtures."""

from __future__ import annotations

import struct
import zlib
from collections.abc import Generator
from pathlib import Path
from typing import Literal

import pytest
from fastapi.testclient import TestClient


def _make_minimal_png() -> bytes:
    """Return bytes for a minimal valid 1x1 white RGB PNG."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )


_MINIMAL_PNG = _make_minimal_png()

# ---------------------------------------------------------------------------
# TestImage — minimal SketchValueProtocol for v3 framework tests
# ---------------------------------------------------------------------------


class TestImage:
    """Minimal SketchValueProtocol implementation for framework tests.

    Stores raw bytes so no image library is needed. Loads by reading the file
    directly.
    """

    extension = "png"
    kind = "image"

    def __init__(self, data: bytes) -> None:
        self._data = data

    @staticmethod
    def load(path: Path) -> TestImage:
        """Load a TestImage from *path* by reading its raw bytes."""
        return TestImage(path.read_bytes())

    def to_bytes(self, mode: Literal["dev", "build"]) -> bytes:
        """Return data prefixed with mode tag so dev and build bytes are distinguishable."""
        return f"mode:{mode}:".encode() + self._data

    def to_html(self, url: str) -> str:
        """Return a minimal HTML img tag."""
        return f'<img src="{url}">'


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------


def make_test_image(path: Path, color: str = "blue") -> None:
    """Write a minimal valid PNG to path. The color argument is ignored."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_MINIMAL_PNG)


def write_test_image(path: Path, color: str = "red") -> None:
    """Overwrite an existing test image with a new color (used in watcher tests)."""
    make_test_image(path, color)


# ---------------------------------------------------------------------------
# tmp_fn_sketch fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_fn_sketch(tmp_path: Path) -> Generator[Path]:
    """Create a temporary sketch directory with a test PNG for v3 @sketch tests."""
    sketch_dir = tmp_path / "hello"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "hello.png")
    yield sketch_dir


# ---------------------------------------------------------------------------
# fn_registry_client_real — wired against the actual sketches/ directory
# ---------------------------------------------------------------------------


@pytest.fixture()
def fn_registry_client_real() -> Generator[TestClient]:
    """TestClient wired to a real SketchFnRegistry against the actual sketches/ directory."""
    from sketchbook.discovery import discover_sketch_fns
    from sketchbook.server.app import create_app
    from sketchbook.server.fn_registry import SketchFnRegistry

    sketches_dir = Path(__file__).parent.parent.parent / "sketches"
    sketch_fns = discover_sketch_fns(sketches_dir)
    fn_registry = SketchFnRegistry(sketch_fns, sketches_dir=sketches_dir)
    app = create_app(fn_registry=fn_registry)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client
