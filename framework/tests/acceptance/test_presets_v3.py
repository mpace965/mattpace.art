# framework/tests/acceptance/test_presets_v3.py

from __future__ import annotations

import json
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


def test_preset_save_load_cycle(fn_registry_client: TestClient, tmp_threshold_sketch: Path) -> None:
    """Save a preset, change params, load it back — params restore."""
    # Trigger lazy load.
    fn_registry_client.get("/sketch/threshold_hello")

    fn_registry_client.patch(
        "/api/sketches/threshold_hello/params",
        json={"step_id": "threshold_image", "param_name": "level", "value": 42},
    )
    resp = fn_registry_client.post(
        "/api/sketches/threshold_hello/presets",
        json={"name": "low"},
    )
    assert resp.status_code == 200
    assert (tmp_threshold_sketch / "presets" / "low.json").exists()

    fn_registry_client.patch(
        "/api/sketches/threshold_hello/params",
        json={"step_id": "threshold_image", "param_name": "level", "value": 200},
    )
    fn_registry_client.post("/api/sketches/threshold_hello/presets/low/load")

    schema = fn_registry_client.get("/api/sketches/threshold_hello/params/threshold_image").json()
    assert schema["level"]["value"] == 42


def test_active_json_written_on_param_change(
    fn_registry_client: TestClient, tmp_threshold_sketch: Path
) -> None:
    """Editing a param writes _active.json with dirty=True."""
    # Trigger lazy load.
    fn_registry_client.get("/sketch/threshold_hello")

    fn_registry_client.patch(
        "/api/sketches/threshold_hello/params",
        json={"step_id": "threshold_image", "param_name": "level", "value": 99},
    )
    active = json.loads((tmp_threshold_sketch / "presets" / "_active.json").read_text())
    assert active["_meta"]["dirty"] is True
    assert active["threshold_image"]["level"] == 99


def test_params_restored_on_reload(
    fn_registry_client: TestClient, tmp_threshold_sketch: Path
) -> None:
    """Active params persisted in _active.json survive a registry reload."""
    # Trigger lazy load.
    fn_registry_client.get("/sketch/threshold_hello")

    fn_registry_client.patch(
        "/api/sketches/threshold_hello/params",
        json={"step_id": "threshold_image", "param_name": "level", "value": 77},
    )
    # Simulate a reload by evicting the DAG from the registry.
    fn_registry_client.app.state.fn_registry.evict("threshold_hello")

    schema = fn_registry_client.get("/api/sketches/threshold_hello/params/threshold_image").json()
    assert schema["level"]["value"] == 77
