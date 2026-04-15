"""Unit tests for BuildingDAG and free functions source()/output()."""

from __future__ import annotations

from pathlib import Path

import pytest

from sketchbook.core.building_dag import (
    BuildingDAG,
    Proxy,
    building_sketch,
    output,
    source,
)


def _loader(path: Path) -> bytes:
    return b""


def _fn_a() -> None:
    pass


def _fn_b() -> None:
    pass


# ---------------------------------------------------------------------------
# allocate_id
# ---------------------------------------------------------------------------


def test_allocate_id_no_collision() -> None:
    """First allocation returns the base name unchanged."""
    dag = BuildingDAG()
    assert dag.allocate_id("blur") == "blur"


def test_allocate_id_collision_appends_suffix() -> None:
    """Second allocation for the same base returns base_1."""
    dag = BuildingDAG()
    dag.allocate_id("blur")
    assert dag.allocate_id("blur") == "blur_1"


def test_allocate_id_multiple_collisions() -> None:
    """Third allocation returns base_2."""
    dag = BuildingDAG()
    dag.allocate_id("blur")
    dag.allocate_id("blur")
    assert dag.allocate_id("blur") == "blur_2"


def test_allocate_id_independent_per_base() -> None:
    """Collision counter is tracked independently per base string."""
    dag = BuildingDAG()
    dag.allocate_id("blur")
    dag.allocate_id("edge")
    assert dag.allocate_id("blur") == "blur_1"
    assert dag.allocate_id("edge") == "edge_1"


# ---------------------------------------------------------------------------
# record_step
# ---------------------------------------------------------------------------


def test_record_step_returns_proxy() -> None:
    """record_step returns a Proxy with the allocated step ID."""
    dag = BuildingDAG()
    proxy = dag.record_step(_fn_a, (), {})
    assert isinstance(proxy, Proxy)
    assert proxy.step_id == "_fn_a"


def test_record_step_twice_collision() -> None:
    """Calling record_step with the same fn twice yields _fn_a and _fn_a_1."""
    dag = BuildingDAG()
    p1 = dag.record_step(_fn_a, (), {})
    p2 = dag.record_step(_fn_a, (), {})
    assert p1.step_id == "_fn_a"
    assert p2.step_id == "_fn_a_1"


def test_record_step_appended_to_steps() -> None:
    """record_step appends a StepCall to the steps list."""
    dag = BuildingDAG()
    dag.record_step(_fn_a, (1, 2), {"x": 3})
    assert len(dag.steps) == 1
    call = dag.steps[0]
    assert call.fn is _fn_a
    assert call.args == (1, 2)
    assert call.kwargs == {"x": 3}


# ---------------------------------------------------------------------------
# record_source
# ---------------------------------------------------------------------------


def test_record_source_returns_proxy_with_stem_id() -> None:
    """record_source allocates an ID from source_<stem>."""
    dag = BuildingDAG()
    proxy = dag.record_source(Path("assets/card.jpg"), _loader)
    assert proxy.step_id == "source_card"


def test_record_source_collision() -> None:
    """Two sources with the same stem get unique IDs."""
    dag = BuildingDAG()
    p1 = dag.record_source(Path("a/card.jpg"), _loader)
    p2 = dag.record_source(Path("b/card.jpg"), _loader)
    assert p1.step_id == "source_card"
    assert p2.step_id == "source_card_1"


# ---------------------------------------------------------------------------
# record_output
# ---------------------------------------------------------------------------


def test_record_output_allocates_id() -> None:
    """record_output allocates output_<name> and appends to outputs list."""
    dag = BuildingDAG()
    proxy = dag.record_step(_fn_a, (), {})
    dag.record_output(proxy, "main", None)
    assert len(dag.outputs) == 1
    rec = dag.outputs[0]
    assert rec.step_id == "output_main"
    assert rec.bundle_name == "main"
    assert rec.source_proxy is proxy
    assert rec.presets is None


def test_record_output_with_presets() -> None:
    """record_output stores the presets list."""
    dag = BuildingDAG()
    proxy = dag.record_step(_fn_a, (), {})
    dag.record_output(proxy, "main", ["soft", "hard"])
    assert dag.outputs[0].presets == ["soft", "hard"]


# ---------------------------------------------------------------------------
# building_sketch context manager
# ---------------------------------------------------------------------------


def test_building_sketch_yields_dag() -> None:
    """building_sketch() yields a fresh BuildingDAG."""
    with building_sketch() as dag:
        assert isinstance(dag, BuildingDAG)


def test_two_contexts_accumulate_independently() -> None:
    """Two separate building_sketch() contexts each accumulate their own calls."""
    with building_sketch() as dag1:
        dag1.record_step(_fn_a, (), {})

    with building_sketch() as dag2:
        dag2.record_step(_fn_b, (), {})
        dag2.record_step(_fn_b, (), {})

    assert len(dag1.steps) == 1
    assert len(dag2.steps) == 2


def test_nested_contexts_isolated() -> None:
    """Nested building_sketch() contexts don't share recorded calls."""
    with building_sketch() as outer:
        outer.record_step(_fn_a, (), {})
        with building_sketch() as inner:
            inner.record_step(_fn_b, (), {})
        outer.record_step(_fn_a, (), {})

    assert len(outer.steps) == 2
    assert len(inner.steps) == 1


# ---------------------------------------------------------------------------
# source() and output() free functions
# ---------------------------------------------------------------------------


def test_source_outside_context_raises() -> None:
    """source() outside building_sketch() raises RuntimeError."""
    with pytest.raises(RuntimeError, match="building_sketch"):
        source("assets/card.jpg", _loader)


def test_output_outside_context_raises() -> None:
    """output() outside building_sketch() raises RuntimeError."""
    with pytest.raises(RuntimeError, match="building_sketch"):
        proxy = Proxy(step_id="fake")
        output(proxy, "main")


def test_source_inside_context_records() -> None:
    """source() inside building_sketch() records a SourceRecord."""
    with building_sketch() as dag:
        proxy = source("assets/photo.jpg", _loader)

    assert isinstance(proxy, Proxy)
    assert proxy.step_id == "source_photo"
    assert len(dag.sources) == 1
    assert dag.sources[0].path == Path("assets/photo.jpg")


def test_output_inside_context_records() -> None:
    """output() inside building_sketch() records an OutputRecord."""
    with building_sketch() as dag:
        proxy = source("assets/photo.jpg", _loader)
        output(proxy, "main")

    assert len(dag.outputs) == 1
    assert dag.outputs[0].bundle_name == "main"
