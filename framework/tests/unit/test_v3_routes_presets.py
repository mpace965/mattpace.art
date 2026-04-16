"""Unit tests for v3 preset routes."""

from __future__ import annotations

import threading
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
    return image


@sketch(date="2026-01-01")
def threshold_hello() -> None:
    """Threshold sketch."""
    img = source("assets/hello.png", TestImage.load)
    result = threshold_image(img)
    output(result, "bundle")


@pytest.fixture()
def tmp_threshold_sketch(tmp_path: Path) -> Generator[Path]:
    """Temporary threshold_hello sketch directory with a test image asset."""
    sketch_dir = tmp_path / "threshold_hello"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "hello.png")
    yield sketch_dir


@pytest.fixture()
def fn_registry_client(tmp_threshold_sketch: Path) -> Generator[TestClient]:
    """TestClient backed by a SketchFnRegistry with the threshold_hello sketch."""
    fn_registry = SketchFnRegistry(
        sketch_fns={"threshold_hello": threshold_hello},
        sketches_dir=tmp_threshold_sketch.parent,
    )
    app = create_app(fn_registry=fn_registry)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


def test_list_presets_empty_initially(
    fn_registry_client: TestClient, tmp_threshold_sketch: Path
) -> None:
    """GET /presets returns empty list and clean active state before any saves."""
    fn_registry_client.get("/sketch/threshold_hello")
    resp = fn_registry_client.get("/api/sketches/threshold_hello/presets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["presets"] == []
    assert data["active"]["dirty"] is False
    assert data["active"]["based_on"] is None


def test_list_presets_shows_saved_preset(
    fn_registry_client: TestClient, tmp_threshold_sketch: Path
) -> None:
    """GET /presets includes named presets after a save."""
    fn_registry_client.get("/sketch/threshold_hello")
    fn_registry_client.post(
        "/api/sketches/threshold_hello/presets",
        json={"name": "snap"},
    )
    resp = fn_registry_client.get("/api/sketches/threshold_hello/presets")
    assert "snap" in resp.json()["presets"]


def test_save_preset_creates_file(
    fn_registry_client: TestClient, tmp_threshold_sketch: Path
) -> None:
    """POST /presets writes a named .json file and returns ok."""
    fn_registry_client.get("/sketch/threshold_hello")
    resp = fn_registry_client.post(
        "/api/sketches/threshold_hello/presets",
        json={"name": "mypreset"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert (tmp_threshold_sketch / "presets" / "mypreset.json").exists()


def test_load_preset_restores_values(
    fn_registry_client: TestClient, tmp_threshold_sketch: Path
) -> None:
    """POST /presets/{name}/load restores param values saved in the preset."""
    fn_registry_client.get("/sketch/threshold_hello")
    fn_registry_client.patch(
        "/api/sketches/threshold_hello/params",
        json={"step_id": "threshold_image", "param_name": "level", "value": 42},
    )
    fn_registry_client.post("/api/sketches/threshold_hello/presets", json={"name": "low"})
    fn_registry_client.patch(
        "/api/sketches/threshold_hello/params",
        json={"step_id": "threshold_image", "param_name": "level", "value": 200},
    )
    resp = fn_registry_client.post("/api/sketches/threshold_hello/presets/low/load")
    assert resp.status_code == 200
    schema = fn_registry_client.get("/api/sketches/threshold_hello/params/threshold_image").json()
    assert schema["level"]["value"] == 42


def test_new_preset_resets_to_defaults(
    fn_registry_client: TestClient, tmp_threshold_sketch: Path
) -> None:
    """POST /presets/new resets all params to their declared defaults."""
    fn_registry_client.get("/sketch/threshold_hello")
    fn_registry_client.patch(
        "/api/sketches/threshold_hello/params",
        json={"step_id": "threshold_image", "param_name": "level", "value": 200},
    )
    resp = fn_registry_client.post("/api/sketches/threshold_hello/presets/new")
    assert resp.status_code == 200
    schema = fn_registry_client.get("/api/sketches/threshold_hello/params/threshold_image").json()
    assert schema["level"]["value"] == 128  # default


def test_load_preset_not_found_returns_404(
    fn_registry_client: TestClient, tmp_threshold_sketch: Path
) -> None:
    """POST /presets/{name}/load returns 404 for an unknown preset name."""
    fn_registry_client.get("/sketch/threshold_hello")
    resp = fn_registry_client.post("/api/sketches/threshold_hello/presets/nonexistent/load")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Regression: preset_state WS broadcast after new / load
# ---------------------------------------------------------------------------


def _collect_until_preset_state(ws, found: threading.Event, messages: list) -> None:
    """Read WS messages into *messages* until preset_state is found or connection closes."""
    try:
        while True:
            msg = ws.receive_json()
            messages.append(msg)
            if msg.get("type") == "preset_state":
                found.set()
                return
    except Exception:
        found.set()  # unblock the waiter so the test doesn't hang on failure


def test_new_preset_broadcasts_preset_state(
    fn_registry_client: TestClient, tmp_threshold_sketch: Path
) -> None:
    """POST /presets/new must broadcast preset_state so the browser refreshes sliders."""
    fn_registry_client.get("/sketch/threshold_hello")

    messages: list[dict] = []
    found = threading.Event()

    with fn_registry_client.websocket_connect("/ws/threshold_hello") as ws:
        t = threading.Thread(
            target=_collect_until_preset_state, args=(ws, found, messages), daemon=True
        )
        t.start()
        fn_registry_client.post("/api/sketches/threshold_hello/presets/new")
        found.wait(timeout=2.0)

    t.join(timeout=1.0)
    assert any(m["type"] == "preset_state" for m in messages)


def test_load_preset_broadcasts_preset_state(
    fn_registry_client: TestClient, tmp_threshold_sketch: Path
) -> None:
    """POST /presets/{name}/load must broadcast preset_state so the browser refreshes sliders."""
    fn_registry_client.get("/sketch/threshold_hello")
    fn_registry_client.patch(
        "/api/sketches/threshold_hello/params",
        json={"step_id": "threshold_image", "param_name": "level", "value": 42},
    )
    fn_registry_client.post("/api/sketches/threshold_hello/presets", json={"name": "low"})

    messages: list[dict] = []
    found = threading.Event()

    with fn_registry_client.websocket_connect("/ws/threshold_hello") as ws:
        t = threading.Thread(
            target=_collect_until_preset_state, args=(ws, found, messages), daemon=True
        )
        t.start()
        fn_registry_client.post("/api/sketches/threshold_hello/presets/low/load")
        found.wait(timeout=2.0)

    t.join(timeout=1.0)
    assert any(m["type"] == "preset_state" for m in messages)
