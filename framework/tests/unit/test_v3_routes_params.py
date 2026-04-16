"""Unit tests for v3 param GET and PATCH endpoints."""

from __future__ import annotations

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
def proc_with_params(
    image: TestImage,
    *,
    level: Annotated[int, Param(min=0, max=255)] = 128,
) -> TestImage:
    """Step with a tunable param."""
    return image


@step
def proc_no_params(image: TestImage) -> TestImage:
    """Step with no params."""
    return image


@sketch(date="2026-01-01")
def param_sketch() -> None:
    """Sketch with a parametrised step."""
    img = source("assets/hello.png", TestImage.load)
    result = proc_with_params(img)
    output(result, "main")


@sketch(date="2026-01-01")
def no_param_sketch() -> None:
    """Sketch with no params."""
    img = source("assets/hello.png", TestImage.load)
    result = proc_no_params(img)
    output(result, "main")


@pytest.fixture()
def _sketch_dir(tmp_path: Path) -> Path:
    """Create sketch directories needed by the registry."""
    for slug in ("param_sketch", "no_param_sketch"):
        d = tmp_path / slug / "assets"
        d.mkdir(parents=True)
        make_test_image(d / "hello.png")
    return tmp_path


@pytest.fixture()
def client(_sketch_dir: Path) -> Generator[TestClient]:
    """TestClient backed by a registry with both test sketches."""
    fn_registry = SketchFnRegistry(
        sketch_fns={
            "param_sketch": param_sketch,
            "no_param_sketch": no_param_sketch,
        },
        sketches_dir=_sketch_dir,
    )
    app = create_app(fn_registry=fn_registry)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/sketches/{sketch_id}/params/{step_id}
# ---------------------------------------------------------------------------


def test_get_step_params_returns_schema(client: TestClient) -> None:
    """GET returns Tweakpane schema for a step with params."""
    client.get("/sketch/param_sketch")  # trigger lazy load
    resp = client.get("/api/sketches/param_sketch/params/proc_with_params")
    assert resp.status_code == 200
    schema = resp.json()
    assert "level" in schema
    assert schema["level"]["type"] == "int"
    assert schema["level"]["value"] == 128


def test_get_step_params_empty_for_no_params(client: TestClient) -> None:
    """GET returns {} for a step with no params."""
    client.get("/sketch/no_param_sketch")
    resp = client.get("/api/sketches/no_param_sketch/params/proc_no_params")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_get_step_params_404_unknown_sketch(client: TestClient) -> None:
    """GET returns 404 for an unknown sketch slug."""
    resp = client.get("/api/sketches/missing/params/proc_with_params")
    assert resp.status_code == 404


def test_get_step_params_404_unknown_step(client: TestClient) -> None:
    """GET returns 404 for an unknown step within a known sketch."""
    client.get("/sketch/param_sketch")
    resp = client.get("/api/sketches/param_sketch/params/nonexistent_step")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/sketches/{sketch_id}/params
# ---------------------------------------------------------------------------


def test_patch_param_returns_ok(client: TestClient) -> None:
    """PATCH with valid payload returns {ok: true}."""
    client.get("/sketch/param_sketch")
    resp = client.patch(
        "/api/sketches/param_sketch/params",
        json={"step_id": "proc_with_params", "param_name": "level", "value": 64},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_patch_param_updates_stored_value(client: TestClient) -> None:
    """PATCH stores the new coerced value in param_values."""
    client.get("/sketch/param_sketch")
    client.patch(
        "/api/sketches/param_sketch/params",
        json={"step_id": "proc_with_params", "param_name": "level", "value": 42},
    )
    # Verify via the schema endpoint — value should now be 42.
    resp = client.get("/api/sketches/param_sketch/params/proc_with_params")
    assert resp.json()["level"]["value"] == 42


def test_patch_param_404_unknown_sketch(client: TestClient) -> None:
    """PATCH returns 404 for an unknown sketch."""
    resp = client.patch(
        "/api/sketches/missing/params",
        json={"step_id": "proc_with_params", "param_name": "level", "value": 64},
    )
    assert resp.status_code == 404


def test_patch_param_404_unknown_step(client: TestClient) -> None:
    """PATCH returns 404 for an unknown step."""
    client.get("/sketch/param_sketch")
    resp = client.patch(
        "/api/sketches/param_sketch/params",
        json={"step_id": "nonexistent", "param_name": "level", "value": 64},
    )
    assert resp.status_code == 404


def test_patch_param_422_unknown_param(client: TestClient) -> None:
    """PATCH returns 422 for an unknown param name."""
    client.get("/sketch/param_sketch")
    resp = client.patch(
        "/api/sketches/param_sketch/params",
        json={"step_id": "proc_with_params", "param_name": "nonexistent", "value": 64},
    )
    assert resp.status_code == 422
