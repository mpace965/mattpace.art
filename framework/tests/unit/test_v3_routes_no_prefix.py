"""Unit tests verifying the /v3 route prefix has been dropped."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import sketch, step
from sketchbook.server.app import create_app
from sketchbook.server.fn_registry import SketchFnRegistry
from tests.conftest import TestImage, make_test_image


@step
def pass_image(image: TestImage) -> TestImage:
    """Return the image unchanged."""
    return image


@sketch(date="2026-04-16")
def cardboard_v3() -> None:
    """Minimal v3 sketch for prefix-drop tests."""
    img = source("assets/hello.png", TestImage.load)
    result = pass_image(img)
    output(result, "main")


@pytest.fixture()
def _sketch_dir(tmp_path: Path) -> Path:
    d = tmp_path / "cardboard_v3" / "assets"
    d.mkdir(parents=True)
    make_test_image(d / "hello.png")
    return tmp_path


@pytest.fixture()
def fn_registry_client(_sketch_dir: Path) -> Generator[TestClient]:
    fn_registry = SketchFnRegistry(
        sketch_fns={"cardboard_v3": cardboard_v3},
        sketches_dir=_sketch_dir,
    )
    app = create_app(fn_registry=fn_registry)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


def test_sketch_route_at_root(fn_registry_client: TestClient) -> None:
    """After the prefix drop, /sketch/{id} hits the v3 route."""
    response = fn_registry_client.get("/sketch/cardboard_v3")
    assert response.status_code == 200


def test_no_v3_prefix_route(fn_registry_client: TestClient) -> None:
    """/v3/sketch/{id} returns 404 — the prefix is gone."""
    response = fn_registry_client.get("/v3/sketch/cardboard_v3")
    assert response.status_code == 404
