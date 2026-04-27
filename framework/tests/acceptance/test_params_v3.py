# tests/acceptance/test_params_v3.py

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Annotated

import pytest
from fastapi.testclient import TestClient

from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step
from sketchbook.server.app import create_app
from sketchbook.server.fn_registry import SketchFnRegistry
from tests.conftest import TestImage, make_test_image


@step
def threshold_image(
    image: TestImage,
    *,
    level: Annotated[int, Param(min=0, max=255, step=1, debounce=150)] = 128,
) -> TestImage:
    """Threshold the image at the given level."""
    return image  # TestImage doesn't actually threshold — result correctness not tested here


@sketch(date="2026-01-01")
def threshold_hello() -> None:
    """Threshold sketch."""
    img = source("assets/hello.png", TestImage.load)
    result = threshold_image(img)
    output(result, "bundle")


@pytest.fixture()
def tmp_threshold_sketch(tmp_path: Path) -> Generator[Path]:
    """Create a temporary sketch directory named 'threshold_hello' with assets."""
    sketch_dir = tmp_path / "threshold_hello"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "hello.png")
    yield sketch_dir


@pytest.fixture()
def fn_registry_client(tmp_threshold_sketch: Path) -> Generator[TestClient]:
    fn_registry = SketchFnRegistry(
        sketch_fns={"threshold_hello": threshold_hello},
        sketches_dir=tmp_threshold_sketch.parent,
    )
    app = create_app(fn_registry=fn_registry)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


def test_param_schema_endpoint(fn_registry_client: TestClient, tmp_threshold_sketch: Path) -> None:
    """The param schema endpoint returns Tweakpane-compatible definitions."""
    # Trigger lazy load
    fn_registry_client.get("/sketch/threshold_hello")

    response = fn_registry_client.get("/api/sketches/threshold_hello/params/threshold_image")
    assert response.status_code == 200
    schema = response.json()
    assert "level" in schema
    assert schema["level"]["min"] == 0
    assert schema["level"]["max"] == 255


def test_param_change_triggers_websocket_update(
    fn_registry_client: TestClient,
    tmp_threshold_sketch: Path,
) -> None:
    """Changing a param via API triggers re-execution and a step_updated WebSocket message."""
    # Trigger lazy load and register watcher.
    fn_registry_client.get("/sketch/threshold_hello")

    received: queue.Queue = queue.Queue()

    def _receive_all(ws) -> None:
        try:
            while True:
                received.put(ws.receive_json())
        except Exception:
            pass

    with fn_registry_client.websocket_connect("/ws/threshold_hello") as ws:
        t = threading.Thread(target=_receive_all, args=(ws,), daemon=True)
        t.start()

        # Drain initial-state messages.
        time.sleep(0.3)
        while not received.empty():
            received.get_nowait()

        response = fn_registry_client.patch(
            "/api/sketches/threshold_hello/params",
            json={"step_id": "threshold_image", "param_name": "level", "value": 64},
        )
        assert response.status_code == 200

        msgs: list[dict] = []
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                msgs.append(received.get(timeout=0.1))
            except queue.Empty:
                if msgs:
                    break
        if not msgs:
            pytest.fail("No WebSocket message received after param change within 5 seconds")

    assert any(
        m["type"] == "step_updated" and m["step_id"] == "threshold_image" for m in msgs
    ), f"No step_updated for threshold_image in {msgs}"
