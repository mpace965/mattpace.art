"""SketchFnRegistry — owns BuiltDAGs, file watchers, and WebSocket state for sketches."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import WebSocket

from sketchbook.core.built_dag import BuiltDAG
from sketchbook.core.decorators import SketchContext
from sketchbook.core.executor import ExecutionResult, execute_built, execute_partial_built
from sketchbook.core.presets import load_active_into_built, save_active_from_built
from sketchbook.core.protocol import SketchValueProtocol, output_kind
from sketchbook.core.watcher import Watcher
from sketchbook.core.wiring import wire_sketch

log = logging.getLogger("sketchbook.server.fn_registry")


class SketchFnRegistry:
    """Owns loaded BuiltDAGs, lazy wiring, file watchers, and WebSocket connections.

    Mirrors SketchRegistry but works with @sketch-decorated functions instead of
    Sketch subclasses.
    """

    def __init__(
        self,
        sketch_fns: dict[str, Callable],
        sketches_dir: Path,
    ) -> None:
        self.sketch_fns: dict[str, Callable] = sketch_fns
        self.sketches_dir: Path = sketches_dir
        self._dags: dict[str, BuiltDAG] = {}
        self._locks: dict[str, threading.Lock] = {slug: threading.Lock() for slug in sketch_fns}
        self._dirty: dict[str, bool] = {}
        self._based_on: dict[str, str | None] = {}
        self._watcher: Watcher | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)

    # ------------------------------------------------------------------
    # DAG access (lazy load on first request)
    # ------------------------------------------------------------------

    def get_dag(self, sketch_id: str) -> BuiltDAG | None:
        """Return the BuiltDAG for *sketch_id*, wiring and executing on first access."""
        if sketch_id in self._dags:
            return self._dags[sketch_id]
        if sketch_id not in self.sketch_fns:
            return None
        with self._locks[sketch_id]:
            if sketch_id in self._dags:
                return self._dags[sketch_id]
            return self._load_dag_lazy(sketch_id)

    def _load_dag_lazy(self, sketch_id: str) -> BuiltDAG | None:
        """Wire and execute a sketch on first access, then register its file watcher."""
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
            execute_built(dag, workdir, mode="dev")
            elapsed = time.perf_counter() - t0
            log.info(f"Loaded sketch '{sketch_id}' ({elapsed:.2f}s)")
            self._dags[sketch_id] = dag
            if self._watcher is not None and self._loop is not None:
                self._register_watch(sketch_id, dag)
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

    def set_param(
        self, sketch_id: str, step_id: str, param_name: str, value: Any
    ) -> ExecutionResult:
        """Store coerced value in BuiltNode.param_values, persist to _active.json, re-execute.

        Coercion is expected to be done by the caller before passing value.
        """
        dag = self._dags.get(sketch_id)
        if dag is None:
            raise KeyError(f"Sketch '{sketch_id}' not in cache — call get_dag first")
        node = dag.nodes[step_id]
        node.param_values[param_name] = value
        self._dirty[sketch_id] = True

        sketch_dir = self.sketches_dir / sketch_id
        presets_dir = sketch_dir / "presets"
        workdir = sketch_dir / ".workdir"
        save_active_from_built(dag, presets_dir, dirty=True, based_on=self._based_on.get(sketch_id))
        return execute_partial_built(dag, [step_id], workdir)

    # ------------------------------------------------------------------
    # Watcher lifecycle
    # ------------------------------------------------------------------

    def start_watcher(self, loop: asyncio.AbstractEventLoop) -> Watcher:
        """Create, populate, and start the file watcher. Return the Watcher."""
        self._loop = loop
        watcher = Watcher()
        self._watcher = watcher
        for sketch_id, dag in self._dags.items():
            self._register_watch(sketch_id, dag)
        watcher.start()
        return watcher

    def stop_watcher(self) -> None:
        """Stop the file watcher and clear references."""
        if self._watcher is not None:
            self._watcher.stop()
        self._watcher = None
        self._loop = None

    def _register_watch(self, sketch_id: str, dag: BuiltDAG) -> None:
        """Watch all source paths in the DAG and re-execute on change."""
        assert self._watcher is not None
        assert self._loop is not None

        sketch_dir = self.sketches_dir / sketch_id
        workdir = sketch_dir / ".workdir"

        for path, source_step_id in dag.source_paths:

            def on_change(
                sid: str = sketch_id,
                d: BuiltDAG = dag,
                nid: str = source_step_id,
                wd: Path = workdir,
            ) -> None:
                log.info(f"Source '{nid}' changed for sketch '{sid}', re-executing")
                result = execute_partial_built(d, [nid], wd)
                asyncio.run_coroutine_threadsafe(
                    self.broadcast_results(sid, d, result),
                    self._loop,  # type: ignore[arg-type]
                )

            self._watcher.watch(path, on_change)

    # ------------------------------------------------------------------
    # WebSocket broadcasts
    # ------------------------------------------------------------------

    async def broadcast(self, sketch_id: str, message: dict[str, Any]) -> None:
        """Push a JSON message to all clients watching *sketch_id*."""
        dead: set[WebSocket] = set()
        for ws in list(self.connections.get(sketch_id, [])):
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.add(ws)
        self.connections[sketch_id] -= dead

    async def broadcast_results(
        self, sketch_id: str, dag: BuiltDAG, result: ExecutionResult
    ) -> None:
        """Broadcast step_updated or step_error for every executed or failed node."""
        for node in dag.topo_sort():
            if node.step_id in result.errors:
                await self.broadcast(
                    sketch_id,
                    {
                        "type": "step_error",
                        "step_id": node.step_id,
                        "error": str(result.errors[node.step_id]),
                    },
                )
            elif node.step_id in result.executed:
                kind = output_kind(node.output)
                is_protocol = isinstance(node.output, SketchValueProtocol)
                ext = node.output.extension if is_protocol else "txt"
                await self.broadcast(
                    sketch_id,
                    {
                        "type": "step_updated",
                        "step_id": node.step_id,
                        "image_url": f"/workdir/{sketch_id}/{node.step_id}.{ext}",
                        "kind": kind,
                    },
                )
