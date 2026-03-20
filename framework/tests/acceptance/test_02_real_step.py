"""Acceptance test 02: A Real Step With Parameters.

Acceptance criteria:
    A sketch using EdgeDetect shows the edge-detected image in the browser.
    The params API returns the Tweakpane-compatible schema.
    Changing a param via the PATCH endpoint triggers re-execution and a
    step_updated WebSocket message.
"""

from __future__ import annotations

import queue
import threading

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_param_schema_endpoint(edge_test_client: TestClient) -> None:
    """The param schema endpoint returns Tweakpane-compatible definitions."""
    response = edge_test_client.get("/api/sketches/edge_hello/params/edge_detect_0")
    assert response.status_code == 200
    schema = response.json()
    assert "low_threshold" in schema["params"]
    assert "high_threshold" in schema["params"]
    assert schema["params"]["low_threshold"]["min"] == 0
    assert schema["params"]["low_threshold"]["max"] == 500
    assert "value" in schema["params"]["low_threshold"]


def test_param_change_triggers_reexecution(edge_test_client: TestClient) -> None:
    """Changing a param via PATCH returns 200 and re-executes the pipeline."""
    response = edge_test_client.patch(
        "/api/sketches/edge_hello/params",
        json={"step_id": "edge_detect_0", "param_name": "low_threshold", "value": 50.0},
    )
    assert response.status_code == 200

    # Verify the param was actually updated
    schema = edge_test_client.get("/api/sketches/edge_hello/params/edge_detect_0").json()
    assert schema["params"]["low_threshold"]["value"] == 50.0


def test_param_change_triggers_websocket_update(
    edge_test_client: TestClient, edge_ws_client
) -> None:
    """Changing a param via PATCH pushes a step_updated message over WebSocket."""
    received: queue.Queue = queue.Queue()

    def _receive_all(ws) -> None:
        try:
            while True:
                received.put(ws.receive_json())
        except Exception as exc:
            received.put(exc)

    with edge_ws_client("/ws/edge_hello") as ws:
        t = threading.Thread(target=_receive_all, args=(ws,), daemon=True)
        t.start()

        edge_test_client.patch(
            "/api/sketches/edge_hello/params",
            json={"step_id": "edge_detect_0", "param_name": "low_threshold", "value": 50.0},
        )

        # Collect messages until we see edge_detect_0 or timeout
        deadline = 5.0
        found = False
        import time
        start = time.monotonic()
        while time.monotonic() - start < deadline:
            try:
                msg = received.get(timeout=0.5)
                if isinstance(msg, Exception):
                    break
                if msg.get("type") == "step_updated" and msg.get("step_id") == "edge_detect_0":
                    found = True
                    break
            except queue.Empty:
                continue

        assert found, "Never received step_updated for edge_detect_0"


def test_step_page_includes_tweakpane(edge_test_client: TestClient) -> None:
    """The step view page includes Tweakpane and the params API endpoint."""
    response = edge_test_client.get("/sketch/edge_hello/step/edge_detect_0")
    assert response.status_code == 200
    assert "tweakpane" in response.text.lower()
