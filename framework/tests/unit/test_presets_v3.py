"""Unit tests for BuiltDAG preset I/O helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sketchbook.core.built_dag import BuiltDAG, BuiltNode, ParamSpec
from sketchbook.core.decorators import Param
from sketchbook.core.presets import (
    load_active_into_built,
    load_preset_into_built,
    reset_to_defaults,
    save_active_from_built,
    save_preset_from_built,
)


@pytest.fixture()
def simple_dag() -> BuiltDAG:
    """A BuiltDAG with one node that has a single int param."""
    dag = BuiltDAG()
    spec = ParamSpec(name="level", type=int, default=128, param=Param(min=0, max=255))
    node = BuiltNode(
        step_id="threshold_image",
        fn=lambda image, *, level=128: image,
        param_schema=[spec],
        param_values={"level": 128},
    )
    dag.nodes["threshold_image"] = node
    return dag


def test_save_active_writes_meta_and_values(tmp_path: Path, simple_dag: BuiltDAG) -> None:
    """save_active_from_built writes _active.json with _meta and param values."""
    presets_dir = tmp_path / "presets"
    simple_dag.nodes["threshold_image"].param_values["level"] = 42
    save_active_from_built(simple_dag, presets_dir, dirty=True, based_on="low")
    data = json.loads((presets_dir / "_active.json").read_text())
    assert data["_meta"]["dirty"] is True
    assert data["_meta"]["based_on"] == "low"
    assert data["threshold_image"]["level"] == 42


def test_load_active_applies_values_to_param_values(tmp_path: Path, simple_dag: BuiltDAG) -> None:
    """load_active_into_built applies values from _active.json to BuiltNode.param_values."""
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    active = {
        "_meta": {"dirty": False, "based_on": "snap"},
        "threshold_image": {"level": 77},
    }
    (presets_dir / "_active.json").write_text(json.dumps(active))
    dirty, based_on = load_active_into_built(simple_dag, presets_dir)
    assert simple_dag.nodes["threshold_image"].param_values["level"] == 77
    assert dirty is False
    assert based_on == "snap"


def test_load_active_no_op_when_missing(tmp_path: Path, simple_dag: BuiltDAG) -> None:
    """load_active_into_built returns (False, None) and leaves values unchanged if absent."""
    presets_dir = tmp_path / "presets"
    dirty, based_on = load_active_into_built(simple_dag, presets_dir)
    assert dirty is False
    assert based_on is None
    assert simple_dag.nodes["threshold_image"].param_values["level"] == 128


def test_save_preset_from_built_writes_named_file(tmp_path: Path, simple_dag: BuiltDAG) -> None:
    """save_preset_from_built writes <name>.json with current param values."""
    presets_dir = tmp_path / "presets"
    simple_dag.nodes["threshold_image"].param_values["level"] = 200
    save_preset_from_built(simple_dag, presets_dir, "bright")
    data = json.loads((presets_dir / "bright.json").read_text())
    assert data["threshold_image"]["level"] == 200


def test_load_preset_into_built_applies_values(tmp_path: Path, simple_dag: BuiltDAG) -> None:
    """load_preset_into_built applies named preset values to param_values."""
    presets_dir = tmp_path / "presets"
    simple_dag.nodes["threshold_image"].param_values["level"] = 50
    save_preset_from_built(simple_dag, presets_dir, "low")
    simple_dag.nodes["threshold_image"].param_values["level"] = 200
    load_preset_into_built(simple_dag, presets_dir, "low")
    assert simple_dag.nodes["threshold_image"].param_values["level"] == 50


def test_load_preset_into_built_not_found_raises(tmp_path: Path, simple_dag: BuiltDAG) -> None:
    """load_preset_into_built raises FileNotFoundError for an unknown preset name."""
    presets_dir = tmp_path / "presets"
    with pytest.raises(FileNotFoundError):
        load_preset_into_built(simple_dag, presets_dir, "nonexistent")


def test_save_active_dirty_flag_true(tmp_path: Path, simple_dag: BuiltDAG) -> None:
    """save_active_from_built with dirty=True writes dirty=True in _meta."""
    presets_dir = tmp_path / "presets"
    save_active_from_built(simple_dag, presets_dir, dirty=True, based_on=None)
    data = json.loads((presets_dir / "_active.json").read_text())
    assert data["_meta"]["dirty"] is True


def test_active_json_based_on_survives_round_trip(tmp_path: Path, simple_dag: BuiltDAG) -> None:
    """based_on written to _active.json is returned by load_active_into_built."""
    presets_dir = tmp_path / "presets"
    save_active_from_built(simple_dag, presets_dir, dirty=False, based_on="mypreset")
    _, based_on = load_active_into_built(simple_dag, presets_dir)
    assert based_on == "mypreset"


def test_reset_to_defaults_restores_all_param_values(simple_dag: BuiltDAG) -> None:
    """reset_to_defaults sets every param_value back to its declared default."""
    simple_dag.nodes["threshold_image"].param_values["level"] = 200
    reset_to_defaults(simple_dag)
    assert simple_dag.nodes["threshold_image"].param_values["level"] == 128


def test_reset_to_defaults_no_op_on_dag_with_no_params() -> None:
    """reset_to_defaults on a node with no params does not raise."""
    from sketchbook.core.built_dag import BuiltNode

    dag = BuiltDAG()
    dag.nodes["source"] = BuiltNode(step_id="source", fn=lambda: None)
    reset_to_defaults(dag)  # must not raise
