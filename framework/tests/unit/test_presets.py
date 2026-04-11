"""Unit tests for PresetManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sketchbook.core.presets import PresetManager
from tests.steps import EdgeDetect

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_dag(tmp_path: Path):
    """A DAG with a single source node (no params)."""
    from sketchbook.core.dag import DAG, DAGNode
    from sketchbook.steps.source import SourceFile

    dag = DAG()
    source = SourceFile(tmp_path / "img.png")
    node = DAGNode(source, "source_photo")
    dag.add_node(node)
    return dag


@pytest.fixture()
def param_dag(tmp_path: Path):
    """A DAG with a source and EdgeDetect node. Returns (dag, node_id, param_name)."""
    from sketchbook.core.dag import DAG, DAGNode
    from sketchbook.steps.source import SourceFile

    dag = DAG()

    source = SourceFile(tmp_path / "img.png")
    source_node = DAGNode(source, "source_photo")
    dag.add_node(source_node)

    step = EdgeDetect()
    node = DAGNode(step, "edge_detect_0")
    dag.add_node(node)
    dag.connect("source_photo", "edge_detect_0", "image")

    return dag, "edge_detect_0", "low_threshold"


# ---------------------------------------------------------------------------
# list_presets
# ---------------------------------------------------------------------------


def test_list_empty_when_presets_dir_missing(tmp_path: Path) -> None:
    """list_presets returns [] when the presets directory does not exist."""
    pm = PresetManager(tmp_path / "presets")
    assert pm.list_presets() == []


def test_list_excludes_active_json(tmp_path: Path, minimal_dag) -> None:
    """list_presets never includes _active in the result."""
    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("a", minimal_dag)
    pm.save_preset("b", minimal_dag)
    result = pm.list_presets()
    assert "_active" not in result
    assert sorted(result) == ["a", "b"]


# ---------------------------------------------------------------------------
# save_preset
# ---------------------------------------------------------------------------


def test_save_preset_creates_named_file(tmp_path: Path, minimal_dag) -> None:
    """save_preset writes <name>.json to the presets directory."""
    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("my_preset", minimal_dag)
    assert (tmp_path / "presets" / "my_preset.json").exists()


def test_save_preset_clears_dirty_flag(tmp_path: Path, minimal_dag) -> None:
    """save_preset clears the dirty flag."""
    pm = PresetManager(tmp_path / "presets")
    pm.mark_dirty()
    assert pm.dirty
    pm.save_preset("my_preset", minimal_dag)
    assert not pm.dirty


def test_save_preset_sets_based_on(tmp_path: Path, minimal_dag) -> None:
    """save_preset sets based_on to the preset name."""
    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("foo", minimal_dag)
    assert pm.based_on == "foo"


def test_save_preset_includes_param_values(tmp_path: Path, param_dag) -> None:
    """save_preset includes the current param values in the JSON file."""
    dag, node_id, param_name = param_dag
    dag.node(node_id).step._param_registry.set_value(param_name, 123.0)
    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("snap", dag)
    data = json.loads((tmp_path / "presets" / "snap.json").read_text())
    assert data[node_id][param_name] == 123.0


def test_save_preset_writes_active_json(tmp_path: Path, minimal_dag) -> None:
    """save_preset also writes _active.json."""
    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("p", minimal_dag)
    assert (tmp_path / "presets" / "_active.json").exists()


# ---------------------------------------------------------------------------
# load_preset
# ---------------------------------------------------------------------------


def test_load_preset_restores_values(tmp_path: Path, param_dag) -> None:
    """load_preset restores param values from the named file."""
    dag, node_id, param_name = param_dag
    pm = PresetManager(tmp_path / "presets")

    dag.node(node_id).step._param_registry.set_value(param_name, 42.0)
    pm.save_preset("snap", dag)

    # Change value after save
    dag.node(node_id).step._param_registry.set_value(param_name, 999.0)

    pm.load_preset("snap", dag)
    assert dag.node(node_id).step._param_registry.get_value(param_name) == 42.0


def test_load_preset_clears_dirty(tmp_path: Path, minimal_dag) -> None:
    """load_preset clears the dirty flag."""
    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("clean", minimal_dag)
    pm.mark_dirty()
    pm.load_preset("clean", minimal_dag)
    assert not pm.dirty


def test_load_preset_sets_based_on(tmp_path: Path, minimal_dag) -> None:
    """load_preset sets based_on to the loaded preset name."""
    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("named", minimal_dag)
    pm.load_preset("named", minimal_dag)
    assert pm.based_on == "named"


def test_load_preset_not_found_raises(tmp_path: Path, minimal_dag) -> None:
    """load_preset raises FileNotFoundError for an unknown preset name."""
    pm = PresetManager(tmp_path / "presets")
    with pytest.raises(FileNotFoundError):
        pm.load_preset("nonexistent", minimal_dag)


def test_load_preset_save_false_skips_active_json(tmp_path: Path, minimal_dag) -> None:
    """load_preset with save=False restores params but does not write _active.json."""
    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("snap", minimal_dag)
    active_path = tmp_path / "presets" / "_active.json"
    mtime_before = active_path.stat().st_mtime

    pm2 = PresetManager(tmp_path / "presets")
    pm2.load_preset("snap", minimal_dag, save=False)

    assert active_path.stat().st_mtime == mtime_before, "_active.json was written unexpectedly"
    assert pm2.based_on == "snap"
    assert not pm2.dirty


# ---------------------------------------------------------------------------
# _active.json round-trip
# ---------------------------------------------------------------------------


def test_active_json_round_trip(tmp_path: Path, param_dag) -> None:
    """save_active + load_active round-trips param values and dirty flag."""
    dag, node_id, param_name = param_dag
    pm = PresetManager(tmp_path / "presets")

    dag.node(node_id).step._param_registry.set_value(param_name, 77.0)
    pm.mark_dirty()
    pm.save_active(dag)

    # Reset to default to confirm load restores
    dag.node(node_id).step._param_registry.set_value(param_name, 100.0)

    pm2 = PresetManager(tmp_path / "presets")
    pm2.load_active(dag)
    assert pm2.dirty
    assert dag.node(node_id).step._param_registry.get_value(param_name) == 77.0


def test_load_active_no_op_when_missing(tmp_path: Path, minimal_dag) -> None:
    """load_active is a no-op when _active.json does not exist."""
    pm = PresetManager(tmp_path / "presets")
    pm.load_active(minimal_dag)  # Should not raise


def test_active_json_stores_meta(tmp_path: Path, minimal_dag) -> None:
    """_active.json includes _meta with dirty and based_on."""
    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("base", minimal_dag)  # sets based_on="base", dirty=False
    data = json.loads((tmp_path / "presets" / "_active.json").read_text())
    assert data["_meta"]["dirty"] is False
    assert data["_meta"]["based_on"] == "base"


# ---------------------------------------------------------------------------
# mark_dirty
# ---------------------------------------------------------------------------


def test_mark_dirty_sets_flag(tmp_path: Path) -> None:
    """mark_dirty sets dirty to True."""
    pm = PresetManager(tmp_path / "presets")
    assert not pm.dirty
    pm.mark_dirty()
    assert pm.dirty


def test_initial_state(tmp_path: Path) -> None:
    """PresetManager starts with dirty=False, based_on=None."""
    pm = PresetManager(tmp_path / "presets")
    assert not pm.dirty
    assert pm.based_on is None


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


def test_reset_clears_dirty_and_based_on(tmp_path: Path, param_dag) -> None:
    """reset() clears dirty flag and based_on."""
    dag, node_id, param_name = param_dag
    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("foo", dag)
    pm.mark_dirty()
    pm.reset(dag)
    assert not pm.dirty
    assert pm.based_on is None


def test_reset_restores_param_defaults(tmp_path: Path, param_dag) -> None:
    """reset() resets all step params to their declared defaults."""
    dag, node_id, param_name = param_dag
    dag.node(node_id).step._param_registry.set_value(param_name, 999.0)
    pm = PresetManager(tmp_path / "presets")
    pm.reset(dag)
    # low_threshold default is 100.0
    assert dag.node(node_id).step._param_registry.get_value(param_name) == 100.0


def test_reset_writes_active_json(tmp_path: Path, minimal_dag) -> None:
    """reset() writes _active.json with dirty=False and based_on=null."""
    import json
    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("p", minimal_dag)
    pm.reset(minimal_dag)
    data = json.loads((tmp_path / "presets" / "_active.json").read_text())
    assert data["_meta"]["dirty"] is False
    assert data["_meta"]["based_on"] is None


# ---------------------------------------------------------------------------
# Color param serialization
# ---------------------------------------------------------------------------


def test_snapshot_params_serializes_color_as_hex(tmp_path: Path) -> None:
    """_snapshot_params with a Color param produces JSON-serializable output."""
    import json
    from typing import Any

    from sketchbook.core.dag import DAG, DAGNode
    from sketchbook.core.params import Color
    from sketchbook.core.step import PipelineStep
    from sketchbook.core.types import Image
    from sketchbook.steps.source import SourceFile

    class TintStep(PipelineStep):
        def setup(self) -> None:
            self.add_input("image", Image)
            self.add_param("tint", Color, default=Color("#ff69b4"))

        def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
            return inputs["image"]

    dag = DAG()
    source = SourceFile(tmp_path / "img.png")
    dag.add_node(DAGNode(source, "source"))
    step = TintStep()
    dag.add_node(DAGNode(step, "tint_step"))
    dag.connect("source", "tint_step", "image")

    pm = PresetManager(tmp_path / "presets")
    # Should not raise — Color must be serializable
    pm.save_active(dag)

    data = json.loads((tmp_path / "presets" / "_active.json").read_text())
    assert data["tint_step"]["tint"] == "#ff69b4"
