"""Unit tests for @step, @sketch, Param, SketchContext, SketchMeta."""

from __future__ import annotations

from sketchbook.core.building_dag import Proxy, building_sketch
from sketchbook.core.decorators import SketchMeta, sketch, step

# ---------------------------------------------------------------------------
# @step
# ---------------------------------------------------------------------------


@step
def _add(x: int, y: int) -> int:
    """Add two integers."""
    return x + y


def test_step_direct_call_executes() -> None:
    """@step called outside building_sketch() executes immediately."""
    result = _add(2, 3)
    assert result == 5


def test_step_inside_context_returns_proxy() -> None:
    """@step called inside building_sketch() returns a Proxy without executing."""
    with building_sketch() as dag:
        result = _add(1, 2)

    assert isinstance(result, Proxy)
    assert result.step_id == "_add"
    # The function should NOT have been called — no output recorded
    assert len(dag.steps) == 1
    # record_step stores the original (unwrapped) function
    assert dag.steps[0].fn is _add.__wrapped__


def test_step_inside_context_does_not_execute() -> None:
    """@step inside building_sketch() defers execution — side-effects don't run."""
    calls: list[int] = []

    @step
    def _side_effect(x: int) -> int:
        calls.append(x)
        return x

    with building_sketch():
        _side_effect(42)

    assert calls == [], "step function should not execute during wiring"


def test_step_records_args_and_kwargs() -> None:
    """Proxy args passed to a @step are recorded in the StepCall."""
    with building_sketch() as dag:
        proxy = _add(1, 2)
        _add(proxy, 3)

    assert dag.steps[1].args[0] is proxy


def test_nested_contexts_isolated() -> None:
    """Two nested building_sketch() contexts are fully isolated."""
    with building_sketch() as outer:
        _add(1, 2)
        with building_sketch() as inner:
            _add(3, 4)
            _add(5, 6)
        _add(7, 8)

    assert len(outer.steps) == 2
    assert len(inner.steps) == 2


# ---------------------------------------------------------------------------
# @sketch
# ---------------------------------------------------------------------------


@sketch(date="2026-01-01")
def my_pipeline() -> None:
    """My great pipeline."""
    pass


def test_sketch_stamps_is_sketch() -> None:
    """@sketch stamps __is_sketch__ = True on the function."""
    assert getattr(my_pipeline, "__is_sketch__", False) is True


def test_sketch_stamps_meta() -> None:
    """@sketch stamps __sketch_meta__ with correct name, date, description."""
    meta: SketchMeta = my_pipeline.__sketch_meta__  # type: ignore[attr-defined]
    assert isinstance(meta, SketchMeta)
    assert meta.date == "2026-01-01"
    assert meta.name == "my_pipeline"
    assert meta.description == "My great pipeline."


def test_sketch_name_from_function_name() -> None:
    """__sketch_meta__.name is derived from the function name, not any argument."""

    @sketch(date="2026-02-01")
    def another_sketch() -> None:
        pass

    assert another_sketch.__sketch_meta__.name == "another_sketch"  # type: ignore[attr-defined]


def test_sketch_description_empty_when_no_docstring() -> None:
    """__sketch_meta__.description is empty string when the function has no docstring."""

    @sketch(date="2026-03-01")
    def no_doc() -> None:
        pass

    assert no_doc.__sketch_meta__.description == ""  # type: ignore[attr-defined]
