"""Acceptance test 03: Preset Persistence.

Acceptance criteria:
    Tweaking params writes to _active.json on disk.
    Saving a named preset copies the active state to <name>.json.
    Loading a named preset restores params to their saved values.
    After a load, the dirty flag is False.
    After an edit, the dirty flag is True.
    Reloading a sketch from disk restores params from _active.json.
    Save/load on one open page propagates preset_state to all connected WebSocket clients.
"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_ws_messages(ws_client, path: str, trigger, *, timeout: float = 5.0) -> list[dict]:
    """Open a WebSocket, call trigger(), collect all messages until timeout."""
    received: queue.Queue = queue.Queue()

    def _reader(ws) -> None:
        try:
            while True:
                received.put(ws.receive_json())
        except Exception as exc:
            received.put(exc)

    with ws_client(path) as ws:
        t = threading.Thread(target=_reader, args=(ws,), daemon=True)
        t.start()
        trigger()
        msgs = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                msg = received.get(timeout=0.2)
                if isinstance(msg, Exception):
                    break
                msgs.append(msg)
            except queue.Empty:
                pass
    return msgs


def test_preset_save_creates_file(tmp_edge_sketch: Path, edge_test_client: TestClient) -> None:
    """Saving a preset writes a named JSON file to the presets directory."""
    edge_test_client.patch(
        "/api/sketches/edge_hello/params",
        json={"step_id": "edge_detect_0", "param_name": "low_threshold", "value": 42.0},
    )
    resp = edge_test_client.post("/api/sketches/edge_hello/presets", json={"name": "low_thresh"})
    assert resp.status_code == 200
    assert (tmp_edge_sketch / "presets" / "low_thresh.json").exists()


def test_preset_save_load_cycle(tmp_edge_sketch: Path, edge_test_client: TestClient) -> None:
    """Save a preset, change params, load it back — params restore."""
    # Tweak a param
    edge_test_client.patch(
        "/api/sketches/edge_hello/params",
        json={"step_id": "edge_detect_0", "param_name": "low_threshold", "value": 42.0},
    )

    # Save as "low_thresh"
    edge_test_client.post("/api/sketches/edge_hello/presets", json={"name": "low_thresh"})
    assert (tmp_edge_sketch / "presets" / "low_thresh.json").exists()

    # Change param again
    edge_test_client.patch(
        "/api/sketches/edge_hello/params",
        json={"step_id": "edge_detect_0", "param_name": "low_threshold", "value": 999.0},
    )

    # Load "low_thresh"
    resp = edge_test_client.post("/api/sketches/edge_hello/presets/low_thresh/load")
    assert resp.status_code == 200

    # Params should be restored
    schema = edge_test_client.get("/api/sketches/edge_hello/params/edge_detect_0").json()
    assert schema["params"]["low_threshold"]["value"] == 42.0


def test_dirty_tracking(edge_test_client: TestClient) -> None:
    """Editing a loaded preset marks it dirty; loading it again clears the flag."""
    edge_test_client.post("/api/sketches/edge_hello/presets", json={"name": "clean"})
    edge_test_client.post("/api/sketches/edge_hello/presets/clean/load")

    # Should be clean after load
    presets = edge_test_client.get("/api/sketches/edge_hello/presets").json()
    assert presets["active"]["dirty"] is False

    # Edit a param
    edge_test_client.patch(
        "/api/sketches/edge_hello/params",
        json={"step_id": "edge_detect_0", "param_name": "low_threshold", "value": 1.0},
    )

    # Should be dirty after edit
    presets = edge_test_client.get("/api/sketches/edge_hello/presets").json()
    assert presets["active"]["dirty"] is True


def test_active_json_written_on_param_change(tmp_edge_sketch: Path, edge_test_client: TestClient) -> None:
    """Changing a param via PATCH writes the new value to _active.json."""
    import json

    edge_test_client.patch(
        "/api/sketches/edge_hello/params",
        json={"step_id": "edge_detect_0", "param_name": "low_threshold", "value": 55.0},
    )
    active_path = tmp_edge_sketch / "presets" / "_active.json"
    assert active_path.exists()
    data = json.loads(active_path.read_text())
    assert data["edge_detect_0"]["low_threshold"] == 55.0


def test_active_persists_across_reload(tmp_edge_sketch: Path) -> None:
    """Params written to _active.json are restored when the sketch is reloaded."""
    from sketchbook.core.executor import execute
    from sketchbook.sketches.edge_hello import EdgeHello

    sketch = EdgeHello(tmp_edge_sketch)
    execute(sketch.dag)

    # Set a value and save to disk
    sketch.dag.node("edge_detect_0").step._param_registry.set_value("low_threshold", 77.0)
    sketch.preset_manager.mark_dirty()
    sketch.preset_manager.save_active(sketch.dag)

    # Reload the sketch from the same directory
    sketch2 = EdgeHello(tmp_edge_sketch)
    val = sketch2.dag.node("edge_detect_0").step._param_registry.get_value("low_threshold")
    assert val == 77.0


def test_list_presets_endpoint(edge_test_client: TestClient) -> None:
    """The list presets endpoint returns named presets and the active meta."""
    edge_test_client.post("/api/sketches/edge_hello/presets", json={"name": "preset_a"})
    edge_test_client.post("/api/sketches/edge_hello/presets", json={"name": "preset_b"})

    resp = edge_test_client.get("/api/sketches/edge_hello/presets")
    assert resp.status_code == 200
    data = resp.json()
    assert "preset_a" in data["presets"]
    assert "preset_b" in data["presets"]
    assert "active" in data
    assert "dirty" in data["active"]


def test_load_unknown_preset_returns_404(edge_test_client: TestClient) -> None:
    """Loading a preset that does not exist returns 404."""
    resp = edge_test_client.post("/api/sketches/edge_hello/presets/does_not_exist/load")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# WebSocket propagation tests
# ---------------------------------------------------------------------------


def test_param_change_broadcasts_preset_state(edge_test_client: TestClient, edge_ws_client) -> None:
    """Changing a param sends a preset_state WebSocket event with dirty=True."""
    msgs = _collect_ws_messages(
        edge_ws_client,
        "/ws/edge_hello",
        lambda: edge_test_client.patch(
            "/api/sketches/edge_hello/params",
            json={"step_id": "edge_detect_0", "param_name": "low_threshold", "value": 10.0},
        ),
        timeout=3.0,
    )
    preset_msgs = [m for m in msgs if m.get("type") == "preset_state"]
    assert preset_msgs, "No preset_state message received after param change"
    assert preset_msgs[-1]["dirty"] is True


def test_preset_save_broadcasts_preset_state(edge_test_client: TestClient, edge_ws_client) -> None:
    """Saving a preset sends a preset_state WebSocket event with dirty=False."""
    msgs = _collect_ws_messages(
        edge_ws_client,
        "/ws/edge_hello",
        lambda: edge_test_client.post(
            "/api/sketches/edge_hello/presets", json={"name": "ws_test"}
        ),
        timeout=3.0,
    )
    preset_msgs = [m for m in msgs if m.get("type") == "preset_state"]
    assert preset_msgs, "No preset_state message received after preset save"
    assert preset_msgs[-1]["dirty"] is False
    assert preset_msgs[-1]["based_on"] == "ws_test"


def test_new_resets_params_and_clears_state(edge_test_client: TestClient) -> None:
    """POST /presets/new resets params to defaults and clears based_on."""
    # Load a preset and dirty it
    edge_test_client.post("/api/sketches/edge_hello/presets", json={"name": "base"})
    edge_test_client.post("/api/sketches/edge_hello/presets/base/load")
    edge_test_client.patch(
        "/api/sketches/edge_hello/params",
        json={"step_id": "edge_detect_0", "param_name": "low_threshold", "value": 42.0},
    )

    resp = edge_test_client.post("/api/sketches/edge_hello/presets/new")
    assert resp.status_code == 200

    # Params should be back to defaults (low_threshold default is 100.0)
    schema = edge_test_client.get("/api/sketches/edge_hello/params/edge_detect_0").json()
    assert schema["params"]["low_threshold"]["value"] == 100.0

    # Active state should be untitled and clean
    presets = edge_test_client.get("/api/sketches/edge_hello/presets").json()
    assert presets["active"]["based_on"] is None
    assert presets["active"]["dirty"] is False


def test_new_broadcasts_preset_state(edge_test_client: TestClient, edge_ws_client) -> None:
    """POST /presets/new broadcasts preset_state with dirty=False, based_on=None."""
    msgs = _collect_ws_messages(
        edge_ws_client,
        "/ws/edge_hello",
        lambda: edge_test_client.post("/api/sketches/edge_hello/presets/new"),
        timeout=3.0,
    )
    preset_msgs = [m for m in msgs if m.get("type") == "preset_state"]
    assert preset_msgs, "No preset_state message received after new"
    assert preset_msgs[-1]["dirty"] is False
    assert preset_msgs[-1]["based_on"] is None


def test_preset_load_broadcasts_preset_state(edge_test_client: TestClient, edge_ws_client) -> None:
    """Loading a preset sends a preset_state WebSocket event with dirty=False."""
    edge_test_client.post("/api/sketches/edge_hello/presets", json={"name": "for_load"})

    msgs = _collect_ws_messages(
        edge_ws_client,
        "/ws/edge_hello",
        lambda: edge_test_client.post(
            "/api/sketches/edge_hello/presets/for_load/load"
        ),
        timeout=3.0,
    )
    preset_msgs = [m for m in msgs if m.get("type") == "preset_state"]
    assert preset_msgs, "No preset_state message received after preset load"
    assert preset_msgs[-1]["dirty"] is False
    assert preset_msgs[-1]["based_on"] == "for_load"
