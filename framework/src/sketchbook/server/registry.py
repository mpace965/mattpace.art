"""SketchRegistry — owns all mutable server state for one app lifetime."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import WebSocket

from sketchbook.core.dag import DAG
from sketchbook.core.executor import ExecutionResult, execute, execute_partial
from sketchbook.core.presets import PresetManager
from sketchbook.core.sketch import Sketch
from sketchbook.core.watcher import Watcher
from sketchbook.steps.source import SourceFile

log = logging.getLogger("sketchbook.server")


class SketchRegistry:
    """Owns loaded sketches, lazy candidates, file watchers, and WebSocket connections.

    One instance is created per app lifetime and stored on ``app.state.registry``.
    Replacing module-level globals with an object scopes all state to the app
    instance, which makes test isolation automatic.
    """

    def __init__(
        self,
        sketches: dict[str, Sketch],
        sketches_dir: Path | None = None,
        *,
        candidates: dict[str, type[Sketch]] | None = None,
    ) -> None:
        self.sketches: dict[str, Sketch] = sketches
        self.sketches_dir: Path | None = sketches_dir
        self.candidates: dict[str, type[Sketch]] = candidates or {}
        self._locks: dict[str, threading.Lock] = {
            slug: threading.Lock() for slug in self.candidates
        }
        self._watched: set[str] = set()
        self._watcher: Watcher | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)

    # ------------------------------------------------------------------
    # Sketch access
    # ------------------------------------------------------------------

    def get_sketch(self, sketch_id: str) -> Sketch | None:
        """Return the sketch for ``sketch_id``, loading it lazily if a candidate exists."""
        if sketch_id in self.sketches:
            return self.sketches[sketch_id]
        if sketch_id not in self.candidates:
            return None
        with self._locks[sketch_id]:
            # Double-check after acquiring the lock.
            if sketch_id in self.sketches:
                return self.sketches[sketch_id]
            return self._load_sketch_lazy(sketch_id)

    def _load_sketch_lazy(self, sketch_id: str) -> Sketch | None:
        """Instantiate and execute a sketch on first access, then register its watcher."""
        cls = self.candidates[sketch_id]
        if self.sketches_dir is None:
            raise RuntimeError("sketches_dir not set — cannot lazy-load sketches")
        sketch_dir = self.sketches_dir / sketch_id
        t0 = time.perf_counter()
        try:
            instance = cls(sketch_dir, mode="dev")
            execute(instance.dag)
            elapsed = time.perf_counter() - t0
            log.info(f"Loaded sketch '{sketch_id}': {cls.name} ({elapsed:.2f}s)")
            self.sketches[sketch_id] = instance
            if self._watcher is not None and self._loop is not None:
                self._register_watch(sketch_id, instance)
            return instance
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            log.warning(f"Failed to load sketch '{sketch_id}': {exc} ({elapsed:.2f}s)")
            # Remove so subsequent requests get a 404 rather than retrying.
            self.candidates.pop(sketch_id, None)
            return None

    def list_sketch_infos(self) -> list[dict[str, str]]:
        """Return display metadata for all known sketches (loaded and candidates).

        Reads class attributes so candidates are included without triggering a load.
        """
        infos: list[dict[str, str]] = []
        seen: set[str] = set()

        for sketch_id, sketch in self.sketches.items():
            cls = type(sketch)
            infos.append(
                {
                    "id": sketch_id,
                    "name": getattr(cls, "name", ""),
                    "description": getattr(cls, "description", ""),
                    "date": getattr(cls, "date", ""),
                }
            )
            seen.add(sketch_id)

        for sketch_id, cls in self.candidates.items():
            if sketch_id not in seen:
                infos.append(
                    {
                        "id": sketch_id,
                        "name": getattr(cls, "name", ""),
                        "description": getattr(cls, "description", ""),
                        "date": getattr(cls, "date", ""),
                    }
                )

        return sorted(infos, key=lambda x: x["date"], reverse=True)

    def get_watched_sketch_ids(self) -> frozenset[str]:
        """Return sketch IDs that currently have file watchers registered."""
        return frozenset(self._watched)

    # ------------------------------------------------------------------
    # Watcher lifecycle
    # ------------------------------------------------------------------

    def start_watcher(self, loop: asyncio.AbstractEventLoop) -> Watcher:
        """Create, populate, and start the file watcher. Return the Watcher."""
        self._loop = loop
        watcher = Watcher()
        self._watcher = watcher
        for sketch_id, sketch in self.sketches.items():
            self._register_watch(sketch_id, sketch)
        watcher.start()
        return watcher

    def stop_watcher(self) -> None:
        """Stop the file watcher and clear watcher/loop references."""
        if self._watcher is not None:
            self._watcher.stop()
        self._watcher = None
        self._loop = None

    def _register_watch(self, sketch_id: str, sketch: Sketch) -> None:
        """Watch all SourceFile nodes in a sketch and re-execute on change."""
        assert self._watcher is not None
        assert self._loop is not None
        self._watched.add(sketch_id)
        for node in sketch.dag.topo_sort():
            if not isinstance(node.step, SourceFile):
                continue

            source_path = node.step._path
            changed_node_id = node.id

            def on_change(
                sid: str = sketch_id,
                sk: Sketch = sketch,
                nid: str = changed_node_id,
            ) -> None:
                log.info(f"Source '{nid}' changed for sketch '{sid}', re-executing descendants")
                result = execute_partial(sk.dag, [nid])
                asyncio.run_coroutine_threadsafe(
                    self.broadcast_results(sid, sk.dag, result),
                    self._loop,  # type: ignore[arg-type]
                )

            self._watcher.watch(source_path, on_change)

    # ------------------------------------------------------------------
    # WebSocket broadcasts
    # ------------------------------------------------------------------

    async def broadcast(self, sketch_id: str, message: dict[str, Any]) -> None:
        """Push a JSON message to all clients watching a sketch."""
        dead: set[WebSocket] = set()
        for ws in list(self.connections.get(sketch_id, [])):
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.add(ws)
        self.connections[sketch_id] -= dead

    async def broadcast_results(self, sketch_id: str, dag: DAG, result: ExecutionResult) -> None:
        """Broadcast step_updated or step_error for every executed or failed node."""
        relevant = result.executed | result.errors.keys()
        for n in dag.topo_sort():
            if not n.workdir_path:
                continue
            if relevant and n.id not in relevant:
                continue
            if n.id in result.errors:
                await self.broadcast(
                    sketch_id,
                    {
                        "type": "step_error",
                        "step_id": n.id,
                        "error": str(result.errors[n.id]),
                    },
                )
            else:
                await self.broadcast(
                    sketch_id,
                    {
                        "type": "step_updated",
                        "step_id": n.id,
                        "image_url": f"/workdir/{sketch_id}/{n.id}.png",
                    },
                )

    async def broadcast_preset_state(self, sketch_id: str, preset_manager: PresetManager) -> None:
        """Broadcast current preset dirty/based_on state to all clients watching a sketch."""
        await self.broadcast(
            sketch_id,
            {
                "type": "preset_state",
                "dirty": preset_manager.dirty,
                "based_on": preset_manager.based_on,
            },
        )
