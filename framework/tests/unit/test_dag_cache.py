"""Unit tests for DagCache — DAG lifecycle, preset state, and execute helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import pytest

from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step
from sketchbook.server.dag_cache import DagCache
from tests.conftest import TestImage, make_test_image


@step
def threshold_image(
    image: TestImage,
    *,
    level: Annotated[int, Param(min=0, max=255, step=1, debounce=150)] = 128,
) -> TestImage:
    """Threshold the image."""
    return image


@sketch(date="2026-01-01")
def threshold_hello() -> None:
    """Single-step threshold sketch."""
    img = source("assets/hello.png", TestImage.load)
    result = threshold_image(img)
    output(result, "bundle")


@pytest.fixture()
def sketch_dir(tmp_path: Path) -> Path:
    d = tmp_path / "threshold_hello" / "assets"
    d.mkdir(parents=True)
    make_test_image(d / "hello.png")
    return tmp_path


@pytest.fixture()
def cache(sketch_dir: Path) -> DagCache:
    return DagCache(
        sketch_fns={"threshold_hello": threshold_hello},
        sketches_dir=sketch_dir,
    )


# ---------------------------------------------------------------------------
# get_dag
# ---------------------------------------------------------------------------


def test_get_dag_wires_and_caches(cache: DagCache, sketch_dir: Path) -> None:
    """get_dag wires the sketch and returns a BuiltDAG on first call."""
    dag = cache.get_dag("threshold_hello")
    assert dag is not None
    assert "threshold_image" in dag.nodes


def test_get_dag_returns_none_for_unknown(cache: DagCache) -> None:
    """get_dag returns None for a sketch slug not in sketch_fns."""
    assert cache.get_dag("does_not_exist") is None


def test_get_dag_returns_same_instance_on_second_call(cache: DagCache) -> None:
    """get_dag returns the cached BuiltDAG without re-wiring."""
    dag1 = cache.get_dag("threshold_hello")
    dag2 = cache.get_dag("threshold_hello")
    assert dag1 is dag2


def test_get_dag_applies_active_json(cache: DagCache, sketch_dir: Path) -> None:
    """get_dag applies _active.json param values on first load."""
    presets_dir = sketch_dir / "threshold_hello" / "presets"
    presets_dir.mkdir()
    active = {
        "_meta": {"dirty": True, "based_on": None},
        "threshold_image": {"level": 42},
    }
    (presets_dir / "_active.json").write_text(json.dumps(active))

    dag = cache.get_dag("threshold_hello")
    assert dag is not None
    assert dag.nodes["threshold_image"].param_values["level"] == 42


# ---------------------------------------------------------------------------
# evict
# ---------------------------------------------------------------------------


def test_evict_forces_rewire_on_next_access(cache: DagCache) -> None:
    """evict removes the cached DAG; the next get_dag returns a new object."""
    dag1 = cache.get_dag("threshold_hello")
    cache.evict("threshold_hello")
    dag2 = cache.get_dag("threshold_hello")
    assert dag1 is not dag2


def test_evict_clears_preset_state(cache: DagCache) -> None:
    """evict removes _dirty and _based_on entries for the sketch."""
    cache.get_dag("threshold_hello")
    cache._dirty["threshold_hello"] = True
    cache._based_on["threshold_hello"] = "snap"
    cache.evict("threshold_hello")
    assert "threshold_hello" not in cache._dirty
    assert "threshold_hello" not in cache._based_on


# ---------------------------------------------------------------------------
# get_last_result / preset state
# ---------------------------------------------------------------------------


def test_get_last_result_returns_none_before_load(cache: DagCache) -> None:
    """get_last_result returns None when the sketch hasn't been loaded yet."""
    assert cache.get_last_result("threshold_hello") is None


def test_get_last_result_after_load(cache: DagCache) -> None:
    """get_last_result returns an ExecutionResult after get_dag loads the sketch."""
    cache.get_dag("threshold_hello")
    result = cache.get_last_result("threshold_hello")
    assert result is not None


def test_get_preset_state_defaults(cache: DagCache) -> None:
    """get_preset_state returns (False, None) before the sketch is loaded."""
    assert cache.get_preset_state("threshold_hello") == (False, None)


def test_set_and_get_preset_state(cache: DagCache) -> None:
    """set_preset_state updates in-memory state; get_preset_state reflects it."""
    cache.set_preset_state("threshold_hello", dirty=True, based_on="snap")
    assert cache.get_preset_state("threshold_hello") == (True, "snap")


# ---------------------------------------------------------------------------
# set_param
# ---------------------------------------------------------------------------


def test_set_param_updates_value_and_writes_active_json(cache: DagCache, sketch_dir: Path) -> None:
    """set_param stores the new value and persists _active.json with dirty=True."""
    cache.get_dag("threshold_hello")
    cache.set_param("threshold_hello", "threshold_image", "level", 99)

    active_path = sketch_dir / "threshold_hello" / "presets" / "_active.json"
    assert active_path.exists()
    data = json.loads(active_path.read_text())
    assert data["_meta"]["dirty"] is True
    assert data["threshold_image"]["level"] == 99


def test_set_param_raises_if_sketch_not_cached(cache: DagCache) -> None:
    """set_param raises KeyError if the sketch has never been loaded."""
    with pytest.raises(KeyError, match="not in cache"):
        cache.set_param("threshold_hello", "threshold_image", "level", 99)


def test_set_param_stores_full_snapshot_in_last_results(cache: DagCache) -> None:
    """After set_param, _last_results holds a full-snapshot result for all nodes."""
    cache.get_dag("threshold_hello")
    cache.set_param("threshold_hello", "threshold_image", "level", 99)

    result = cache.get_last_result("threshold_hello")
    assert result is not None
    # Full snapshot includes both the source node and the reexecuted step
    assert "source_hello" in result.outputs
    assert "threshold_image" in result.outputs


# ---------------------------------------------------------------------------
# save_preset
# ---------------------------------------------------------------------------


def test_save_preset_writes_file_and_updates_state(cache: DagCache, sketch_dir: Path) -> None:
    """save_preset writes <name>.json and clears dirty / sets based_on."""
    cache.get_dag("threshold_hello")
    cache._dirty["threshold_hello"] = True
    cache.save_preset("threshold_hello", "mypreset")

    preset_path = sketch_dir / "threshold_hello" / "presets" / "mypreset.json"
    assert preset_path.exists()
    dirty, based_on = cache.get_preset_state("threshold_hello")
    assert dirty is False
    assert based_on == "mypreset"


def test_save_preset_raises_if_sketch_not_cached(cache: DagCache) -> None:
    """save_preset raises KeyError if the sketch has never been loaded."""
    with pytest.raises(KeyError, match="not in cache"):
        cache.save_preset("threshold_hello", "snap")


# ---------------------------------------------------------------------------
# reset_to_defaults_and_execute
# ---------------------------------------------------------------------------


def test_reset_to_defaults_and_execute_restores_defaults(cache: DagCache, sketch_dir: Path) -> None:
    """reset_to_defaults_and_execute resets param_values and clears dirty state."""
    cache.get_dag("threshold_hello")
    cache.set_param("threshold_hello", "threshold_image", "level", 200)
    cache.reset_to_defaults_and_execute("threshold_hello")

    dag = cache.get_dag("threshold_hello")
    assert dag is not None
    assert dag.nodes["threshold_image"].param_values["level"] == 128
    dirty, based_on = cache.get_preset_state("threshold_hello")
    assert dirty is False
    assert based_on is None


# ---------------------------------------------------------------------------
# load_preset_and_execute
# ---------------------------------------------------------------------------


def test_load_preset_and_execute_applies_preset_values(cache: DagCache, sketch_dir: Path) -> None:
    """load_preset_and_execute restores param values from a saved preset."""
    cache.get_dag("threshold_hello")
    cache.set_param("threshold_hello", "threshold_image", "level", 42)
    cache.save_preset("threshold_hello", "low")
    cache.set_param("threshold_hello", "threshold_image", "level", 200)

    cache.load_preset_and_execute("threshold_hello", "low")

    dag = cache.get_dag("threshold_hello")
    assert dag is not None
    assert dag.nodes["threshold_image"].param_values["level"] == 42
    dirty, based_on = cache.get_preset_state("threshold_hello")
    assert dirty is False
    assert based_on == "low"


def test_load_preset_and_execute_raises_for_missing_preset(
    cache: DagCache, sketch_dir: Path
) -> None:
    """load_preset_and_execute propagates FileNotFoundError for unknown preset."""
    cache.get_dag("threshold_hello")
    with pytest.raises(FileNotFoundError):
        cache.load_preset_and_execute("threshold_hello", "nonexistent")


# ---------------------------------------------------------------------------
# Ordering: _active.json must not be written before execution completes
# ---------------------------------------------------------------------------


def test_set_param_does_not_write_active_json_when_execution_fails(
    cache: DagCache, sketch_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """set_param does not persist _active.json when execution raises."""
    cache.get_dag("threshold_hello")
    active_path = sketch_dir / "threshold_hello" / "presets" / "_active.json"
    active_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "sketchbook.server.dag_cache.execute_partial_built",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        cache.set_param("threshold_hello", "threshold_image", "level", 99)

    assert not active_path.exists()


def test_reset_to_defaults_does_not_write_active_json_when_execution_fails(
    cache: DagCache, sketch_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """reset_to_defaults_and_execute does not persist _active.json when execution raises."""
    cache.get_dag("threshold_hello")
    active_path = sketch_dir / "threshold_hello" / "presets" / "_active.json"
    # Remove any _active.json written during initial load so the assertion is clean.
    active_path.unlink(missing_ok=True)

    monkeypatch.setattr(
        "sketchbook.server.dag_cache.execute_built",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        cache.reset_to_defaults_and_execute("threshold_hello")

    assert not active_path.exists()


def test_load_preset_does_not_write_active_json_when_execution_fails(
    cache: DagCache, sketch_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_preset_and_execute does not update _active.json when execution raises."""
    cache.get_dag("threshold_hello")
    # Save a preset so load_preset_and_execute has something to load.
    cache.set_param("threshold_hello", "threshold_image", "level", 42)
    cache.save_preset("threshold_hello", "snap")

    active_path = sketch_dir / "threshold_hello" / "presets" / "_active.json"
    original_content = active_path.read_text()

    monkeypatch.setattr(
        "sketchbook.server.dag_cache.execute_built",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        cache.load_preset_and_execute("threshold_hello", "snap")

    assert active_path.read_text() == original_content
