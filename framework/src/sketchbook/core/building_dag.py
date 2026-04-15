"""BuildingDAG and supporting types — records step calls during sketch wiring."""

from __future__ import annotations

import contextlib
from collections import defaultdict
from collections.abc import Callable, Generator
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Proxy:
    """Represents a deferred step result during sketch wiring. Carries the step ID."""

    step_id: str


@dataclass
class StepCall:
    """Records one @step function call made during sketch wiring."""

    step_id: str
    fn: Callable
    args: tuple
    kwargs: dict


@dataclass
class SourceRecord:
    """Records a source() call made during sketch wiring."""

    step_id: str
    path: Path
    loader: Callable


@dataclass
class OutputRecord:
    """Records an output() call made during sketch wiring."""

    step_id: str
    source_proxy: Proxy
    bundle_name: str
    presets: list[str] | None


class BuildingDAG:
    """Lightweight structure accumulated as a sketch function runs.

    Separates sources, step calls, and output declarations into three lists.
    All IDs are unique within a single BuildingDAG instance.
    """

    def __init__(self) -> None:
        self._steps: list[StepCall] = []
        self._sources: list[SourceRecord] = []
        self._outputs: list[OutputRecord] = []
        self._id_counts: dict[str, int] = defaultdict(int)

    @property
    def steps(self) -> list[StepCall]:
        """Return all recorded step calls in wiring order."""
        return list(self._steps)

    @property
    def sources(self) -> list[SourceRecord]:
        """Return all recorded source declarations in wiring order."""
        return list(self._sources)

    @property
    def outputs(self) -> list[OutputRecord]:
        """Return all recorded output declarations in wiring order."""
        return list(self._outputs)

    def allocate_id(self, base: str) -> str:
        """Return a unique ID derived from base, appending _1, _2, … on collision."""
        count = self._id_counts[base]
        self._id_counts[base] += 1
        return base if count == 0 else f"{base}_{count}"

    def record_step(self, fn: Callable, args: tuple, kwargs: dict) -> Proxy:
        """Record a step call and return a Proxy for its (deferred) result."""
        step_id = self.allocate_id(fn.__name__)
        self._steps.append(StepCall(step_id=step_id, fn=fn, args=args, kwargs=kwargs))
        return Proxy(step_id=step_id)

    def record_source(self, path: Path, loader: Callable) -> Proxy:
        """Record a source file declaration and return a Proxy for the loaded value."""
        step_id = self.allocate_id(f"source_{path.stem}")
        self._sources.append(SourceRecord(step_id=step_id, path=path, loader=loader))
        return Proxy(step_id=step_id)

    def record_output(self, proxy: Proxy, bundle_name: str, presets: list[str] | None) -> None:
        """Record an output declaration."""
        step_id = self.allocate_id(f"output_{bundle_name}")
        self._outputs.append(
            OutputRecord(
                step_id=step_id,
                source_proxy=proxy,
                bundle_name=bundle_name,
                presets=presets,
            )
        )


# ---------------------------------------------------------------------------
# Module-level ContextVar holding the active BuildingDAG
# ---------------------------------------------------------------------------

_active_dag: ContextVar[BuildingDAG | None] = ContextVar("_active_dag", default=None)


@contextlib.contextmanager
def building_sketch() -> Generator[BuildingDAG]:
    """Activate a fresh BuildingDAG for the duration of the block.

    Nested invocations are isolated — each gets its own BuildingDAG and the
    previous context is fully restored on exit.
    """
    dag = BuildingDAG()
    token = _active_dag.set(dag)
    try:
        yield dag
    finally:
        _active_dag.reset(token)


# ---------------------------------------------------------------------------
# Free functions for sketch authors
# ---------------------------------------------------------------------------


def source(path: str | Path, loader: Callable) -> Proxy:
    """Declare a source file input in the current sketch context.

    Raises RuntimeError if called outside a building_sketch() context.
    """
    dag = _active_dag.get()
    if dag is None:
        raise RuntimeError("source() called outside a building_sketch() context")
    return dag.record_source(Path(path), loader)


def output(proxy: Proxy, name: str, *, presets: list[str] | None = None) -> None:
    """Declare an output node in the current sketch context.

    Raises RuntimeError if called outside a building_sketch() context.
    """
    dag = _active_dag.get()
    if dag is None:
        raise RuntimeError("output() called outside a building_sketch() context")
    dag.record_output(proxy, name, presets)
