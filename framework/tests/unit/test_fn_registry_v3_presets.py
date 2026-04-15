"""Unit tests for SketchFnRegistry preset state: active load, evict, set_param."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Annotated

import pytest

from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step
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


def test_load_dag_applies_active_json_on_first_access(tmp_threshold_sketch: Path) -> None:
    """_load_dag_lazy calls load_active_into_built; _active.json values appear in param_values."""
    presets_dir = tmp_threshold_sketch / "presets"
    presets_dir.mkdir()
    active = {
        "_meta": {"dirty": True, "based_on": None},
        "threshold_image": {"level": 42},
    }
    (presets_dir / "_active.json").write_text(json.dumps(active))

    registry = SketchFnRegistry(
        sketch_fns={"threshold_hello": threshold_hello},
        sketches_dir=tmp_threshold_sketch.parent,
    )
    dag = registry.get_dag("threshold_hello")
    assert dag is not None
    assert dag.nodes["threshold_image"].param_values["level"] == 42


def test_evict_forces_reload_on_next_access(tmp_threshold_sketch: Path) -> None:
    """evict() removes the cached DAG; the next get_dag call returns a new object."""
    registry = SketchFnRegistry(
        sketch_fns={"threshold_hello": threshold_hello},
        sketches_dir=tmp_threshold_sketch.parent,
    )
    dag1 = registry.get_dag("threshold_hello")
    assert dag1 is not None
    registry.evict("threshold_hello")
    dag2 = registry.get_dag("threshold_hello")
    assert dag2 is not None
    assert dag1 is not dag2


def test_param_update_writes_active_json(tmp_threshold_sketch: Path) -> None:
    """set_param writes _active.json with dirty=True and the new value."""
    registry = SketchFnRegistry(
        sketch_fns={"threshold_hello": threshold_hello},
        sketches_dir=tmp_threshold_sketch.parent,
    )
    registry.get_dag("threshold_hello")
    registry.set_param("threshold_hello", "threshold_image", "level", 99)

    active_path = tmp_threshold_sketch / "presets" / "_active.json"
    assert active_path.exists()
    data = json.loads(active_path.read_text())
    assert data["_meta"]["dirty"] is True
    assert data["threshold_image"]["level"] == 99
