"""Acceptance test: upstream failure propagates step_blocked to downstream nodes.

Acceptance criteria:
    A @sketch with a failing source and two chained downstream steps:
    1. The failing source broadcasts a step_error message over /ws/<sketch>.
    2. Each downstream node broadcasts a step_blocked message (not step_error).
    3. No step_updated message is sent for any node in the failed pipeline.

This test covers the server-side half of the red-dot-on-blocked-nodes fix.
The browser-side JS handler that adds the visible class is manual-only per CLAUDE.md.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import sketch, step
from sketchbook.server.app import create_app
from sketchbook.server.fn_registry import SketchFnRegistry
from tests.conftest import TestImage

# ---------------------------------------------------------------------------
# Sketch with a missing source asset so the first node always errors
# ---------------------------------------------------------------------------


@step
def ep_downstream_a(image: TestImage) -> TestImage:
    """Pass image through unchanged."""
    return image


@step
def ep_downstream_b(image: TestImage) -> TestImage:
    """Pass image through unchanged."""
    return image


@sketch(date="2026-04-19")
def ep_failing_source_sketch() -> None:
    """Sketch whose source asset does not exist — exercises error propagation."""
    img = source("assets/missing.png", TestImage.load)
    a = ep_downstream_a(img)
    b = ep_downstream_b(a)
    output(b, "main")


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def failing_client(tmp_path: Path) -> Generator[TestClient]:
    """TestClient for ep_failing_source_sketch with no asset on disk."""
    sketch_dir = tmp_path / "failing"
    sketch_dir.mkdir()
    (sketch_dir / "assets").mkdir()
    # Deliberately do NOT write assets/missing.png.
    fn_registry = SketchFnRegistry(
        sketch_fns={"failing": ep_failing_source_sketch},
        sketches_dir=tmp_path,
    )
    app = create_app(fn_registry=fn_registry)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _collect_initial_ws_messages(
    client: TestClient, sketch_id: str, drain_s: float = 0.5
) -> list[dict]:
    """Connect, collect the burst of initial-state messages, then disconnect."""
    received: queue.Queue[dict] = queue.Queue()

    def _recv(ws) -> None:
        try:
            while True:
                received.put(ws.receive_json())
        except Exception:
            pass

    msgs: list[dict] = []
    with client.websocket_connect(f"/ws/{sketch_id}") as ws:
        t = threading.Thread(target=_recv, args=(ws,), daemon=True)
        t.start()
        time.sleep(drain_s)

    while not received.empty():
        msgs.append(received.get_nowait())
    return msgs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_failing_source_broadcasts_step_error(failing_client: TestClient) -> None:
    """The failing source node sends a step_error message with the error text."""
    failing_client.get("/sketch/failing")
    msgs = _collect_initial_ws_messages(failing_client, "failing")

    error_msgs = [m for m in msgs if m.get("type") == "step_error"]
    assert error_msgs, f"Expected at least one step_error, got: {msgs}"
    assert any(m.get("error") for m in error_msgs), (
        "step_error should carry a non-empty error string"
    )


def test_blocked_downstream_nodes_broadcast_step_blocked(failing_client: TestClient) -> None:
    """Downstream nodes affected by the upstream failure receive step_blocked, not step_error."""
    failing_client.get("/sketch/failing")
    msgs = _collect_initial_ws_messages(failing_client, "failing")

    blocked = {m["step_id"] for m in msgs if m.get("type") == "step_blocked"}
    assert "ep_downstream_a" in blocked, f"Expected step_blocked for ep_downstream_a. Got: {msgs}"
    assert "ep_downstream_b" in blocked, f"Expected step_blocked for ep_downstream_b. Got: {msgs}"


def test_no_step_updated_on_failed_pipeline(failing_client: TestClient) -> None:
    """No step_updated message is sent when the pipeline fails at the source."""
    failing_client.get("/sketch/failing")
    msgs = _collect_initial_ws_messages(failing_client, "failing")

    updated = [m for m in msgs if m.get("type") == "step_updated"]
    assert not updated, f"Unexpected step_updated messages on failed pipeline: {updated}"
