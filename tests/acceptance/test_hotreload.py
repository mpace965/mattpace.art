"""Acceptance test 04: Hot-reload support.

Acceptance criteria:
    The dev app factory (used by uvicorn reload mode) creates a working app
    from scratch on each restart.

    On WebSocket connect, the browser immediately receives step_updated messages
    so it shows current state after a server restart without a manual trigger.
"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import write_test_image


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_dev_app_factory_creates_working_app() -> None:
    """create_dev_app() returns a FastAPI app that handles requests."""
    from sketchbook.server._dev import create_dev_app

    app = create_dev_app()
    with TestClient(app) as client:
        # App may have no sketches if assets aren't present — 404 is fine.
        resp = client.get("/sketch/nonexistent/step/foo")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Initial state push
# ---------------------------------------------------------------------------


def test_websocket_sends_initial_state_on_connect(test_client: TestClient, ws_client) -> None:
    """On WebSocket connect, step_updated is immediately pushed for all current outputs."""
    received: queue.Queue = queue.Queue()

    def _receive_all(ws) -> None:
        try:
            while True:
                received.put(ws.receive_json())
        except Exception:
            pass

    with ws_client("/ws/hello") as ws:
        t = threading.Thread(target=_receive_all, args=(ws,), daemon=True)
        t.start()

        # Initial messages arrive immediately after connect; give them a moment.
        time.sleep(0.3)

        messages = []
        while not received.empty():
            messages.append(received.get_nowait())

    assert messages, "No messages received on connect"
    step_ids = {m["step_id"] for m in messages if m.get("type") == "step_updated"}
    assert "passthrough_0" in step_ids, f"Expected passthrough_0 in initial state, got: {step_ids}"



# ---------------------------------------------------------------------------
# File change still works after initial-state push is added
# ---------------------------------------------------------------------------


def test_file_change_triggers_websocket_update_after_initial_flush(
    tmp_sketch: Path,
    test_client: TestClient,
    ws_client,
) -> None:
    """Overwriting the source image pushes a new step_updated after initial state is drained."""
    received: queue.Queue = queue.Queue()

    def _receive_all(ws) -> None:
        try:
            while True:
                received.put(ws.receive_json())
        except Exception:
            pass

    with ws_client("/ws/hello") as ws:
        t = threading.Thread(target=_receive_all, args=(ws,), daemon=True)
        t.start()

        # Drain initial-state messages sent immediately on connect.
        time.sleep(0.3)
        while not received.empty():
            received.get_nowait()

        # Trigger a file change.
        write_test_image(tmp_sketch / "assets" / "fence-torn-paper.png", color="red")

        try:
            msg = received.get(timeout=5.0)
        except queue.Empty:
            pytest.fail("No WebSocket message received after file change within 5 seconds")

        assert msg["type"] == "step_updated"
        assert "image_url" in msg
