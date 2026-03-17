"""Acceptance test 01: Walking Skeleton.

Acceptance criteria:
    A sketch with one source and one passthrough step shows the image in
    the browser. Overwriting the source file on disk pushes a step_updated
    message over WebSocket without a manual page refresh.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import write_test_image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_img_src(html: str) -> str:
    """Return the src attribute of the first <img> tag in html."""
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
    assert match, f"No <img src=...> found in HTML:\n{html}"
    return match.group(1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_source_to_passthrough_shows_in_browser(test_client: TestClient) -> None:
    """The step page returns HTML containing an <img> tag."""
    response = test_client.get("/sketch/hello/step/passthrough_0")
    assert response.status_code == 200
    assert "<img" in response.text


def test_step_image_url_resolves_to_image_bytes(test_client: TestClient) -> None:
    """The <img> src in the step page resolves to actual image bytes."""
    response = test_client.get("/sketch/hello/step/passthrough_0")
    assert response.status_code == 200

    img_url = extract_img_src(response.text)
    img_response = test_client.get(img_url)
    assert img_response.status_code == 200
    assert img_response.headers["content-type"].startswith("image/")


def test_file_change_triggers_websocket_update(tmp_sketch: Path, test_client: TestClient, ws_client) -> None:
    """Overwriting the source image pushes a step_updated message over WebSocket."""
    import queue
    import threading

    received: queue.Queue = queue.Queue()

    def _receive(ws) -> None:
        try:
            received.put(ws.receive_json())
        except Exception as exc:
            received.put(exc)

    with ws_client("/ws/hello") as ws:
        t = threading.Thread(target=_receive, args=(ws,), daemon=True)
        t.start()

        # Overwrite the source image with a red image
        write_test_image(tmp_sketch / "assets" / "fence-torn-paper.png", color="red")

        try:
            msg = received.get(timeout=5.0)
        except queue.Empty:
            pytest.fail("No WebSocket message received within 5 seconds")

        if isinstance(msg, Exception):
            pytest.fail(f"WebSocket receive raised: {msg}")

        assert msg["type"] == "step_updated"
        assert "image_url" in msg
