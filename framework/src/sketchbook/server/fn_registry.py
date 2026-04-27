"""SketchFnRegistry — thin facade over DagCache, WatcherCoordinator, and ConnectionManager."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import WebSocket

from sketchbook.core.built_dag import BuiltDAG
from sketchbook.core.executor import ExecutionResult
from sketchbook.core.watcher import Watcher
from sketchbook.server.connection_manager import ConnectionManager, _is_cascaded  # noqa: F401
from sketchbook.server.dag_cache import DagCache
from sketchbook.server.watcher_coordinator import WatcherCoordinator

log = logging.getLogger("sketchbook.server.fn_registry")


class SketchFnRegistry:
    """Facade that coordinates DagCache, WatcherCoordinator, and ConnectionManager.

    Keeps a stable public surface so route handlers and tests need minimal changes.
    """

    def __init__(self, sketch_fns: dict[str, Callable], sketches_dir: Path) -> None:
        self.sketch_fns = sketch_fns
        self.sketches_dir = sketches_dir
        self._dag_cache = DagCache(sketch_fns, sketches_dir)
        self._connection_manager = ConnectionManager()
        self._watcher_coordinator = WatcherCoordinator(self._dag_cache, self._connection_manager)

    # ------------------------------------------------------------------
    # DAG access
    # ------------------------------------------------------------------

    def get_dag(self, sketch_id: str) -> BuiltDAG | None:
        """Return the BuiltDAG for sketch_id, wiring and executing on first access."""
        dag = self._dag_cache.get_dag(sketch_id)
        if dag is not None:
            self._watcher_coordinator.register_watch_if_active(sketch_id, dag)
        return dag

    def evict(self, slug: str) -> None:
        """Remove a cached BuiltDAG so the next get_dag call re-wires and re-executes."""
        self._dag_cache.evict(slug)

    def set_param(
        self, sketch_id: str, step_id: str, param_name: str, value: Any
    ) -> ExecutionResult:
        """Store coerced value in param_values, persist _active.json, and re-execute."""
        return self._dag_cache.set_param(sketch_id, step_id, param_name, value)

    def save_preset(self, sketch_id: str, name: str) -> None:
        """Snapshot current param values as a named preset and update active state."""
        self._dag_cache.save_preset(sketch_id, name)

    def reset_to_defaults_and_execute(self, sketch_id: str) -> ExecutionResult:
        """Reset all params to declared defaults, persist _active.json, and re-execute."""
        return self._dag_cache.reset_to_defaults_and_execute(sketch_id)

    def load_preset_and_execute(self, sketch_id: str, name: str) -> ExecutionResult:
        """Load a named preset into the DAG, persist _active.json, and re-execute."""
        return self._dag_cache.load_preset_and_execute(sketch_id, name)

    def get_preset_state(self, sketch_id: str) -> tuple[bool, str | None]:
        """Return (dirty, based_on) for sketch_id."""
        return self._dag_cache.get_preset_state(sketch_id)

    def get_last_result(self, sketch_id: str) -> ExecutionResult | None:
        """Return the most recent ExecutionResult for sketch_id, or None."""
        return self._dag_cache.get_last_result(sketch_id)

    # ------------------------------------------------------------------
    # Watcher lifecycle
    # ------------------------------------------------------------------

    def start_watcher(self, loop: asyncio.AbstractEventLoop) -> Watcher:
        """Create, populate, and start the file watcher. Return the Watcher."""
        return self._watcher_coordinator.start(loop)

    def stop_watcher(self) -> None:
        """Stop the file watcher and clear all references."""
        self._watcher_coordinator.stop()

    # ------------------------------------------------------------------
    # WebSocket management
    # ------------------------------------------------------------------

    @property
    def connections(self) -> dict[str, set[WebSocket]]:
        """Active WebSocket connections keyed by sketch_id."""
        return self._connection_manager.connections

    async def broadcast(self, sketch_id: str, message: dict[str, Any]) -> None:
        """Push a JSON message to all clients watching sketch_id."""
        await self._connection_manager.broadcast(sketch_id, message)

    async def broadcast_results(
        self, sketch_id: str, dag: BuiltDAG, result: ExecutionResult
    ) -> None:
        """Broadcast step_updated, step_error, or step_blocked for every node."""
        await self._connection_manager.broadcast_results(sketch_id, dag, result)

    async def dump_initial_state(
        self,
        websocket: WebSocket,
        sketch_id: str,
        dag: BuiltDAG,
        workdir: Path,
        last_result: ExecutionResult | None,
    ) -> None:
        """Push current output state to a freshly connected WebSocket client."""
        await self._connection_manager.dump_initial_state(
            websocket, sketch_id, dag, workdir, last_result
        )

    # ------------------------------------------------------------------
    # Internal access for tests and backward compat
    # ------------------------------------------------------------------

    @property
    def _exec_locks(self) -> dict[str, threading.Lock]:
        """Per-sketch execution locks (exposed for concurrency tests)."""
        return self._dag_cache._exec_locks
