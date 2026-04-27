"""DagCache — BuiltDAG lifecycle, lazy wiring/execution, and preset dirty state."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sketchbook.core.built_dag import BuiltDAG
from sketchbook.core.decorators import SketchContext
from sketchbook.core.executor import ExecutionResult, execute_built, execute_partial_built
from sketchbook.core.presets import (
    load_active_into_built,
    load_preset_into_built,
    reset_to_defaults,
    save_active_from_built,
    save_preset_from_built,
)
from sketchbook.core.wiring import wire_sketch

log = logging.getLogger("sketchbook.server.dag_cache")


class DagCache:
    """Caches BuiltDAGs, lazy-wires sketches on first access, and owns preset dirty state."""

    def __init__(self, sketch_fns: dict[str, Callable], sketches_dir: Path) -> None:
        self.sketch_fns = sketch_fns
        self.sketches_dir = sketches_dir
        self._dags: dict[str, BuiltDAG] = {}
        # Guards initial _wire_and_execute per sketch (double-checked locking pattern).
        # Safe under CPython's GIL: the outer check is a fast-path read; the inner
        # re-check after acquiring prevents a second goroutine that was blocked at
        # the lock from re-wiring an already-populated entry.
        self._locks: dict[str, threading.Lock] = {slug: threading.Lock() for slug in sketch_fns}
        # Serialises all mutation+execution sequences per sketch across the asyncio
        # event-loop thread (route handlers) and the watchdog observer thread (on_change).
        self._exec_locks: dict[str, threading.Lock] = {
            slug: threading.Lock() for slug in sketch_fns
        }
        self._dirty: dict[str, bool] = {}
        self._based_on: dict[str, str | None] = {}
        self._last_results: dict[str, ExecutionResult] = {}

    def get_dag(self, sketch_id: str) -> BuiltDAG | None:
        """Return the BuiltDAG for sketch_id, wiring and executing on first access."""
        if sketch_id in self._dags:
            return self._dags[sketch_id]
        if sketch_id not in self.sketch_fns:
            return None
        with self._locks[sketch_id]:
            if sketch_id in self._dags:
                return self._dags[sketch_id]
            return self._wire_and_execute(sketch_id)

    def _wire_and_execute(self, sketch_id: str) -> BuiltDAG | None:
        """Wire, load active preset, and execute a sketch; cache and return the BuiltDAG."""
        fn = self.sketch_fns[sketch_id]
        sketch_dir = self.sketches_dir / sketch_id
        workdir = sketch_dir / ".workdir"
        ctx = SketchContext(mode="dev")
        t0 = time.perf_counter()
        try:
            dag = wire_sketch(fn, ctx, sketch_dir=sketch_dir)
            presets_dir = sketch_dir / "presets"
            self._dirty[sketch_id], self._based_on[sketch_id] = load_active_into_built(
                dag, presets_dir
            )
            self._last_results[sketch_id] = execute_built(dag, workdir, mode="dev")
            elapsed = time.perf_counter() - t0
            log.info(f"Loaded sketch '{sketch_id}' ({elapsed:.2f}s)")
            self._dags[sketch_id] = dag
            return dag
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            log.warning(f"Failed to load sketch '{sketch_id}': {exc} ({elapsed:.2f}s)")
            return None

    def evict(self, slug: str) -> None:
        """Remove a cached BuiltDAG so the next get_dag call re-wires and re-executes."""
        self._dags.pop(slug, None)
        self._dirty.pop(slug, None)
        self._based_on.pop(slug, None)
        self._last_results.pop(slug, None)

    def get_last_result(self, sketch_id: str) -> ExecutionResult | None:
        """Return the most recent ExecutionResult for sketch_id, or None."""
        return self._last_results.get(sketch_id)

    def get_preset_state(self, sketch_id: str) -> tuple[bool, str | None]:
        """Return (dirty, based_on) for sketch_id."""
        return self._dirty.get(sketch_id, False), self._based_on.get(sketch_id)

    def set_preset_state(self, sketch_id: str, dirty: bool, based_on: str | None) -> None:
        """Update in-memory preset dirty and based_on for sketch_id."""
        self._dirty[sketch_id] = dirty
        self._based_on[sketch_id] = based_on

    def set_param(
        self, sketch_id: str, step_id: str, param_name: str, value: Any
    ) -> ExecutionResult:
        """Store coerced value in param_values, persist _active.json, and re-execute."""
        dag = self._dags.get(sketch_id)
        if dag is None:
            raise KeyError(f"Sketch '{sketch_id}' not in cache — call get_dag first")
        node = dag.nodes[step_id]
        sketch_dir = self.sketches_dir / sketch_id
        presets_dir = sketch_dir / "presets"
        workdir = sketch_dir / ".workdir"
        with self._exec_locks[sketch_id]:
            node.param_values[param_name] = value
            self._dirty[sketch_id] = True
            based_on = self._based_on.get(sketch_id)
            save_active_from_built(dag, presets_dir, dirty=True, based_on=based_on)
            result = execute_partial_built(dag, [step_id], workdir)
            self._last_results[sketch_id] = result
            return result

    def save_preset(self, sketch_id: str, name: str) -> None:
        """Snapshot current param values as a named preset and update active state.

        Does not re-execute — saving is pure persistence on already-applied values.
        """
        dag = self._dags.get(sketch_id)
        if dag is None:
            raise KeyError(f"Sketch '{sketch_id}' not in cache — call get_dag first")
        sketch_dir = self.sketches_dir / sketch_id
        presets_dir = sketch_dir / "presets"
        save_preset_from_built(dag, presets_dir, name)
        self._dirty[sketch_id] = False
        self._based_on[sketch_id] = name
        save_active_from_built(dag, presets_dir, dirty=False, based_on=name)

    def reset_to_defaults_and_execute(self, sketch_id: str) -> ExecutionResult:
        """Reset all params to declared defaults, persist _active.json, and re-execute."""
        dag = self._dags.get(sketch_id)
        if dag is None:
            raise KeyError(f"Sketch '{sketch_id}' not in cache — call get_dag first")
        sketch_dir = self.sketches_dir / sketch_id
        presets_dir = sketch_dir / "presets"
        workdir = sketch_dir / ".workdir"
        with self._exec_locks[sketch_id]:
            reset_to_defaults(dag)
            self._dirty[sketch_id] = False
            self._based_on[sketch_id] = None
            save_active_from_built(dag, presets_dir, dirty=False, based_on=None)
            result = execute_built(dag, workdir)
            self._last_results[sketch_id] = result
            return result

    def load_preset_and_execute(self, sketch_id: str, name: str) -> ExecutionResult:
        """Load a named preset into the DAG, persist _active.json, and re-execute."""
        dag = self._dags.get(sketch_id)
        if dag is None:
            raise KeyError(f"Sketch '{sketch_id}' not in cache — call get_dag first")
        sketch_dir = self.sketches_dir / sketch_id
        presets_dir = sketch_dir / "presets"
        workdir = sketch_dir / ".workdir"
        with self._exec_locks[sketch_id]:
            load_preset_into_built(dag, presets_dir, name)
            self._dirty[sketch_id] = False
            self._based_on[sketch_id] = name
            save_active_from_built(dag, presets_dir, dirty=False, based_on=name)
            result = execute_built(dag, workdir)
            self._last_results[sketch_id] = result
            return result
