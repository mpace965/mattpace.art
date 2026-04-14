#!/usr/bin/env python3
"""
Spike: proxy mechanism for @step functions.

Answers open question #1 from docs/simplified-framework-technical-context.md:
"How does @step know it's being called from a sketch context vs. directly?"

Approach: ContextVar[BuildingDAG | None] + explicit context manager.

Proves:
  1. ContextVar correctly scopes across sketch_fn() -> step_fn() call chain.
  2. Proxy roundtrip works: step args are Proxies during wiring, real values at execution.
  3. Direct call (outside sketch context) bypasses proxy and executes immediately.
  4. Nested building_sketch() contexts are isolated from each other.
  5. ID collision resolution (same function called twice in one sketch).

Run with: uv run python docs/spike_proxy_mechanism.py
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Generator
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Annotated, Any, TypeVar


# ---------------------------------------------------------------------------
# Value type (userland in real design; minimal stand-in for the spike)
# ---------------------------------------------------------------------------


@dataclass
class FakeImage:
    """Minimal stand-in for a real Image type."""

    data: str

    def __repr__(self) -> str:
        return f"FakeImage({self.data!r})"


# ---------------------------------------------------------------------------
# Param annotation (framework protocol, lives in core/params.py for real)
# ---------------------------------------------------------------------------


@dataclass
class Param:
    """Metadata attached to a tunable parameter via Annotated[T, Param(...)]."""

    min: float | None = None
    max: float | None = None
    step: float | None = None
    label: str | None = None
    debounce: int | None = None


# ---------------------------------------------------------------------------
# Proxy: deferred step result recorded in the DAG
# ---------------------------------------------------------------------------


@dataclass
class StepCall:
    """Records one step call made during sketch wiring."""

    step_id: str
    fn: Callable[..., Any]
    args: tuple[Any, ...]  # may contain Proxy objects
    kwargs: dict[str, Any]


@dataclass
class Proxy:
    """Represents a deferred step result. Carries the step ID for edge resolution."""

    step_id: str
    _dag: BuildingDAG = field(repr=False)

    def __repr__(self) -> str:
        return f"Proxy({self.step_id!r})"


# ---------------------------------------------------------------------------
# BuildingDAG: records calls implicitly during sketch function execution
# ---------------------------------------------------------------------------


class BuildingDAG:
    """Lightweight structure built as the sketch function runs."""

    def __init__(self) -> None:
        self._calls: list[StepCall] = []
        self._id_counts: dict[str, int] = {}

    def _allocate_id(self, name: str) -> str:
        """Return a unique step ID, appending _1, _2... on collision."""
        count = self._id_counts.get(name, 0)
        self._id_counts[name] = count + 1
        return name if count == 0 else f"{name}_{count}"

    def record(self, fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Proxy:
        """Record a step call and return a Proxy for the (deferred) result."""
        step_id = self._allocate_id(fn.__name__)
        self._calls.append(StepCall(step_id=step_id, fn=fn, args=args, kwargs=kwargs))
        return Proxy(step_id=step_id, _dag=self)

    @property
    def calls(self) -> list[StepCall]:
        """Return all recorded calls in wiring order."""
        return list(self._calls)


# ---------------------------------------------------------------------------
# ContextVar: the active DAG, if any
# ---------------------------------------------------------------------------

_active_dag: ContextVar[BuildingDAG | None] = ContextVar("_active_dag", default=None)


@contextlib.contextmanager
def building_sketch() -> Generator[BuildingDAG, None, None]:
    """Activate a new BuildingDAG for the duration of the block.

    Properly restores the previous context on exit, so nesting is safe.
    """
    dag = BuildingDAG()
    token = _active_dag.set(dag)
    try:
        yield dag
    finally:
        _active_dag.reset(token)


# ---------------------------------------------------------------------------
# @step decorator
# ---------------------------------------------------------------------------

F = TypeVar("F", bound=Callable[..., Any])


def step(fn: F) -> F:
    """Mark a function as a pipeline step.

    - Called from a sketch context: records the call in the active DAG and
      returns a Proxy for the (not-yet-computed) result.
    - Called directly: executes immediately with real values.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        dag = _active_dag.get()
        if dag is not None:
            return dag.record(fn, args, kwargs)
        return fn(*args, **kwargs)

    wrapper.__name__ = fn.__name__  # type: ignore[attr-defined]
    wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Minimal executor: resolves Proxies and executes calls in wiring order
# ---------------------------------------------------------------------------


def execute(dag: BuildingDAG) -> dict[str, Any]:
    """Execute all recorded step calls, returning outputs keyed by step ID."""
    outputs: dict[str, Any] = {}

    def resolve(v: Any) -> Any:
        return outputs[v.step_id] if isinstance(v, Proxy) else v

    for call in dag.calls:
        real_args = tuple(resolve(a) for a in call.args)
        real_kwargs = {k: resolve(v) for k, v in call.kwargs.items()}
        outputs[call.step_id] = call.fn(*real_args, **real_kwargs)

    return outputs


# ---------------------------------------------------------------------------
# Example steps (userland — what a sketch author writes)
# ---------------------------------------------------------------------------


@step
def load_photo(path: str) -> FakeImage:
    """Load an image from disk."""
    return FakeImage(f"loaded:{path}")


@step
def circle_grid_mask(
    image: FakeImage,
    *,
    count: Annotated[int, Param(min=1, max=20, step=1, debounce=150)] = 3,
    radius: Annotated[float, Param(min=0.0, max=1.0, step=0.01)] = 0.75,
) -> FakeImage:
    """Draw a uniform grid of filled circles on a black background."""
    return FakeImage(f"mask(count={count},radius={radius})")


@step
def difference_blend(image: FakeImage, mask: FakeImage) -> FakeImage:
    """Return the per-pixel absolute difference of image and mask."""
    return FakeImage(f"blend({image.data},{mask.data})")


# ---------------------------------------------------------------------------
# Example sketch (what a sketch author writes)
# ---------------------------------------------------------------------------


def cardboard() -> BuildingDAG:
    """Wire up the cardboard sketch and return the resulting DAG."""
    with building_sketch() as dag:
        photo = load_photo("assets/cardboard.jpg")
        mask = circle_grid_mask(photo, count=4)
        _result = difference_blend(photo, mask)
    return dag


# ---------------------------------------------------------------------------
# Spike: run assertions, print results
# ---------------------------------------------------------------------------


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def main() -> None:
    print("=== Spike: proxy mechanism (ContextVar approach) ===")

    # 1. Wiring phase: sketch function runs, steps return Proxies
    section("1. Wiring phase")
    dag = cardboard()
    for call in dag.calls:
        print(f"  {call.step_id}: args={call.args}  kwargs={call.kwargs}")

    assert len(dag.calls) == 3, f"Expected 3 calls, got {len(dag.calls)}"
    assert dag.calls[0].step_id == "load_photo"
    assert dag.calls[1].step_id == "circle_grid_mask"
    assert dag.calls[2].step_id == "difference_blend"

    # circle_grid_mask received a Proxy from load_photo
    proxy_arg = dag.calls[1].args[0]
    assert isinstance(proxy_arg, Proxy), f"Expected Proxy, got {type(proxy_arg)}"
    assert proxy_arg.step_id == "load_photo"

    # kwargs are plain Python (the count=4 override)
    assert dag.calls[1].kwargs == {"count": 4}

    print("  OK: 3 calls recorded; Proxies carry correct step IDs")

    # 2. Execution phase: executor resolves Proxies and calls real functions
    section("2. Execution phase")
    outputs = execute(dag)
    for step_id, out in outputs.items():
        print(f"  {step_id} -> {out}")

    assert isinstance(outputs["load_photo"], FakeImage)
    assert isinstance(outputs["circle_grid_mask"], FakeImage)
    assert isinstance(outputs["difference_blend"], FakeImage)
    assert outputs["difference_blend"].data == (
        "blend(loaded:assets/cardboard.jpg,mask(count=4,radius=0.75))"
    ), outputs["difference_blend"].data
    print("  OK: Proxies resolved; real values flowed through the chain")

    # 3. Direct call: step executes immediately, no Proxy involved
    section("3. Direct call (outside sketch context)")
    direct = circle_grid_mask(FakeImage("raw_input"), count=2, radius=0.5)
    print(f"  result: {direct}")
    assert isinstance(direct, FakeImage), f"Expected FakeImage, got {type(direct)}"
    assert direct.data == "mask(count=2,radius=0.5)"
    print("  OK: direct call executes immediately, returns real value")

    # 4. ContextVar isolation: nested contexts are independent
    section("4. Nested context isolation")
    with building_sketch() as dag_outer:
        load_photo("outer_a.jpg")
        with building_sketch() as dag_inner:
            load_photo("inner.jpg")
        load_photo("outer_b.jpg")

    assert len(dag_outer.calls) == 2, f"Expected 2 outer calls, got {len(dag_outer.calls)}"
    assert len(dag_inner.calls) == 1, f"Expected 1 inner call, got {len(dag_inner.calls)}"
    assert dag_outer.calls[0].args == ("outer_a.jpg",)
    assert dag_outer.calls[1].args == ("outer_b.jpg",)
    assert dag_inner.calls[0].args == ("inner.jpg",)
    print(f"  dag_outer: {[c.step_id for c in dag_outer.calls]}")
    print(f"  dag_inner: {[c.step_id for c in dag_inner.calls]}")
    print("  OK: nested contexts don't bleed into each other")

    # 5. ID collision resolution: same step called twice gets unique IDs
    section("5. ID collision resolution")
    with building_sketch() as dag_dup:
        load_photo("first.jpg")
        load_photo("second.jpg")

    ids = [c.step_id for c in dag_dup.calls]
    print(f"  IDs: {ids}")
    assert ids == ["load_photo", "load_photo_1"], f"Unexpected IDs: {ids}"
    print("  OK: second call gets _1 suffix, no collision")

    print("\n=== All assertions passed. ContextVar + context manager is viable. ===\n")


if __name__ == "__main__":
    main()
