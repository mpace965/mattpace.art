"""Acceptance test: sketch load errors surface as 500 with traceback, not silent 404.

Acceptance criteria:
    When a sketch's build() raises an exception, visiting /sketch/<id>:
    - Returns HTTP 500 (not 404)
    - Renders an HTML page containing the exception type and message
    - Renders the full stack trace so the user can see where the error is
    - Keeps the candidate registered so a page refresh retries the load
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sketchbook.core.sketch import Sketch
from sketchbook.server.app import create_app


class _BrokenSketch(Sketch):
    """Sketch whose build() always raises — simulates a coding mistake."""

    name = "Broken"
    description = "Always fails to load."
    date = "2026-01-01"

    def build(self) -> None:
        """Raise unconditionally to simulate a broken sketch."""
        raise RuntimeError("intentional build error for testing")


def _make_client(tmp_path: Path) -> TestClient:
    sketch_dir = tmp_path / "broken"
    sketch_dir.mkdir()
    app = create_app({}, sketches_dir=tmp_path, candidates={"broken": _BrokenSketch})
    return TestClient(app, raise_server_exceptions=False)


def test_broken_sketch_returns_500(tmp_path: Path) -> None:
    """A sketch that raises during build returns HTTP 500, not 404."""
    with _make_client(tmp_path) as client:
        resp = client.get("/sketch/broken")
    assert resp.status_code == 500


def test_broken_sketch_error_page_contains_exception_message(tmp_path: Path) -> None:
    """The 500 page includes the exception message."""
    with _make_client(tmp_path) as client:
        resp = client.get("/sketch/broken")
    assert "intentional build error for testing" in resp.text


def test_broken_sketch_error_page_contains_traceback(tmp_path: Path) -> None:
    """The 500 page includes a traceback so the user can locate the error."""
    with _make_client(tmp_path) as client:
        resp = client.get("/sketch/broken")
    assert "Traceback" in resp.text
    assert "build" in resp.text


def test_broken_sketch_candidate_survives_failed_load(tmp_path: Path) -> None:
    """After a failed load the candidate is still registered, so refresh retries."""
    sketch_dir = tmp_path / "broken"
    sketch_dir.mkdir()
    app = create_app({}, sketches_dir=tmp_path, candidates={"broken": _BrokenSketch})

    with TestClient(app, raise_server_exceptions=False) as client:
        # First request fails.
        resp1 = client.get("/sketch/broken")
        assert resp1.status_code == 500

        # Second request still gets an error page, not a 404.
        resp2 = client.get("/sketch/broken")
        assert resp2.status_code == 500
        assert "intentional build error for testing" in resp2.text


def test_nonexistent_sketch_still_returns_404(tmp_path: Path) -> None:
    """A sketch that was never registered still returns 404, not 500."""
    app = create_app({}, sketches_dir=tmp_path, candidates={})
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/sketch/nonexistent")
    assert resp.status_code == 404
