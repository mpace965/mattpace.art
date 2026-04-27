"""ConnectionManager — WebSocket connection tracking and broadcast fan-out."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import WebSocket

from sketchbook.core.built_dag import BuiltDAG
from sketchbook.core.executor import ExecutionResult
from sketchbook.core.protocol import SketchValueProtocol, output_kind

log = logging.getLogger("sketchbook.server.connection_manager")


def _is_cascaded(exc: Exception) -> bool:
    """Return True if exc is a downstream propagation of an upstream failure."""
    return isinstance(exc, RuntimeError) and str(exc).startswith("No output — upstream failure")


class ConnectionManager:
    """Tracks active WebSocket connections per sketch and pushes execution results."""

    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)

    def add(self, sketch_id: str, websocket: WebSocket) -> None:
        """Register a new WebSocket connection for sketch_id."""
        self.connections[sketch_id].add(websocket)

    def discard(self, sketch_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection for sketch_id."""
        self.connections[sketch_id].discard(websocket)

    async def broadcast(self, sketch_id: str, message: dict[str, Any]) -> None:
        """Push a JSON message to all clients watching sketch_id."""
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
        """Broadcast step_updated, step_error, or step_blocked for every node."""
        for node in dag.nodes_in_order():
            if node.step_id in result.errors:
                exc = result.errors[node.step_id]
                if _is_cascaded(exc):
                    await self.broadcast(
                        sketch_id, {"type": "step_blocked", "step_id": node.step_id}
                    )
                else:
                    await self.broadcast(
                        sketch_id,
                        {"type": "step_error", "step_id": node.step_id, "error": str(exc)},
                    )
            elif node.step_id in result.executed:
                kind = output_kind(node.output)
                is_protocol = isinstance(node.output, SketchValueProtocol)
                ext = node.output.extension if is_protocol else "txt"
                elapsed = result.timings.get(node.step_id)
                msg: dict[str, Any] = {
                    "type": "step_updated",
                    "step_id": node.step_id,
                    "image_url": f"/workdir/{sketch_id}/{node.step_id}.{ext}",
                    "kind": kind,
                    "elapsed_ms": round(elapsed * 1000, 1) if elapsed is not None else None,
                }
                await self.broadcast(sketch_id, msg)
            elif node.output is not None:
                await self.broadcast(sketch_id, {"type": "step_cached", "step_id": node.step_id})

    async def dump_initial_state(
        self,
        websocket: WebSocket,
        sketch_id: str,
        dag: BuiltDAG,
        workdir: Path,
        last_result: ExecutionResult | None,
    ) -> None:
        """Push current output state to a freshly connected WebSocket client."""
        for node in dag.nodes_in_order():
            if last_result is not None and node.step_id in last_result.errors:
                exc = last_result.errors[node.step_id]
                if _is_cascaded(exc):
                    await websocket.send_text(
                        json.dumps({"type": "step_blocked", "step_id": node.step_id})
                    )
                else:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "step_error",
                                "step_id": node.step_id,
                                "error": str(exc),
                            }
                        )
                    )
            elif node.output is not None:
                kind = output_kind(node.output)
                is_proto = isinstance(node.output, SketchValueProtocol)
                ext = node.output.extension if is_proto else "txt"
                if (workdir / f"{node.step_id}.{ext}").exists():
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "step_updated",
                                "step_id": node.step_id,
                                "image_url": f"/workdir/{sketch_id}/{node.step_id}.{ext}",
                                "kind": kind,
                            }
                        )
                    )
