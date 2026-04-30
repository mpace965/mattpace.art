"""WatcherCoordinator — file watcher lifecycle and per-sketch path registration."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from functools import partial
from pathlib import Path

from sketchbook.core.built_dag import BuiltDAG
from sketchbook.core.executor import execute_partial_built
from sketchbook.core.watcher import Watcher
from sketchbook.server.connection_manager import ConnectionManager
from sketchbook.server.dag_cache import DagCache

log = logging.getLogger("sketchbook.server.watcher_coordinator")


def _log_broadcast_future(future: concurrent.futures.Future[None], *, sid: str, nid: str) -> None:
    """Log any exception from a broadcast_results coroutine with sketch and step context."""
    exc = future.exception()
    if exc is not None:
        log.error(f"broadcast_results failed for '{sid}' after '{nid}' changed", exc_info=exc)


class WatcherCoordinator:
    """Owns the Watcher instance and registers per-path callbacks for each sketch."""

    def __init__(self, dag_cache: DagCache, connection_manager: ConnectionManager) -> None:
        self._dag_cache = dag_cache
        self._connection_manager = connection_manager
        self._watcher: Watcher | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._registered: set[str] = set()

    def start(self, loop: asyncio.AbstractEventLoop) -> Watcher:
        """Create and start the file watcher, registering any already-cached DAGs."""
        self._loop = loop
        watcher = Watcher()
        self._watcher = watcher
        for sketch_id, dag in self._dag_cache._dags.items():
            self._register_watch(sketch_id, dag)
            self._registered.add(sketch_id)
        watcher.start()
        return watcher

    def stop(self) -> None:
        """Stop the file watcher and clear all references."""
        if self._watcher is not None:
            self._watcher.stop()
        self._watcher = None
        self._loop = None
        self._registered.clear()

    def register_watch_if_active(self, sketch_id: str, dag: BuiltDAG) -> None:
        """Register file watchers for dag if the watcher is running (idempotent)."""
        if (
            self._watcher is not None
            and self._loop is not None
            and sketch_id not in self._registered
        ):
            self._registered.add(sketch_id)
            self._register_watch(sketch_id, dag)

    def _register_watch(self, sketch_id: str, dag: BuiltDAG) -> None:
        """Watch every source path in dag and call _on_source_change on modification."""
        assert self._watcher is not None
        workdir = self._dag_cache.sketches_dir / sketch_id / ".workdir"
        for path, source_step_id in dag.source_paths:
            callback = partial(
                self._on_source_change,
                sketch_id=sketch_id,
                dag=dag,
                source_step_id=source_step_id,
                workdir=workdir,
            )
            self._watcher.watch(path, callback)

    def _on_source_change(
        self,
        *,
        sketch_id: str,
        dag: BuiltDAG,
        source_step_id: str,
        workdir: Path,
    ) -> None:
        """Re-execute from source_step_id and broadcast results to connected clients."""
        log.info(f"Source '{source_step_id}' changed for sketch '{sketch_id}', re-executing")
        loop = self._loop
        if loop is None:
            log.warning(f"File-change for '{sketch_id}' arrived after watcher stopped; skipping")
            return
        with self._dag_cache._exec_locks[sketch_id]:
            prior = self._dag_cache._last_results[sketch_id]
            result = execute_partial_built(dag, [source_step_id], workdir, prior=prior)
        self._dag_cache._last_results[sketch_id] = result
        future = asyncio.run_coroutine_threadsafe(
            self._connection_manager.broadcast_results(sketch_id, dag, result),
            loop,
        )
        future.add_done_callback(partial(_log_broadcast_future, sid=sketch_id, nid=source_step_id))
