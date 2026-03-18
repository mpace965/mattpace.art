"""WebSocket endpoint for live step updates."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger("sketchbook.server.ws")

router = APIRouter()

# sketch_id -> set of connected WebSocket clients
_connections: dict[str, set[WebSocket]] = defaultdict(set)


@router.websocket("/ws/{sketch_id}")
async def ws_endpoint(websocket: WebSocket, sketch_id: str) -> None:
    """Accept a WebSocket connection, push current state, then hold open for push updates."""
    from sketchbook.server.app import get_sketch

    await websocket.accept()
    _connections[sketch_id].add(websocket)
    log.info(f"WebSocket connected for sketch '{sketch_id}'")

    # Push current output state so the browser is up-to-date immediately after
    # reconnecting (e.g. following a server hot-reload).
    sketch = get_sketch(sketch_id)
    if sketch is not None:
        for node in sketch.dag.topo_sort():
            if node.workdir_path and Path(node.workdir_path).exists():
                await websocket.send_text(
                    json.dumps({
                        "type": "step_updated",
                        "step_id": node.id,
                        "image_url": f"/workdir/{sketch_id}/{node.id}.png",
                    })
                )

    try:
        # Block until the client disconnects. We don't expect incoming messages,
        # but receive() is the correct way to detect a close — asyncio.sleep()
        # never notices the connection has gone away.
        await websocket.receive()
    except WebSocketDisconnect:
        pass
    finally:
        _connections[sketch_id].discard(websocket)
        log.info(f"WebSocket disconnected for sketch '{sketch_id}'")


async def broadcast(sketch_id: str, message: dict) -> None:
    """Push a JSON message to all clients watching a sketch."""
    dead: set[WebSocket] = set()
    for ws in list(_connections.get(sketch_id, [])):
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            dead.add(ws)
    _connections[sketch_id] -= dead


async def broadcast_preset_state(sketch_id: str, preset_manager) -> None:
    """Broadcast current preset dirty/based_on state to all clients watching a sketch."""
    await broadcast(sketch_id, {
        "type": "preset_state",
        "dirty": preset_manager.dirty,
        "based_on": preset_manager.based_on,
    })


async def broadcast_results(sketch_id: str, dag, result) -> None:
    """Broadcast step_updated or step_error for every executed or failed node with a workdir path."""
    relevant = result.executed | result.errors.keys()
    for n in dag.topo_sort():
        if not n.workdir_path:
            continue
        if relevant and n.id not in relevant:
            continue
        if n.id in result.errors:
            await broadcast(sketch_id, {
                "type": "step_error",
                "step_id": n.id,
                "error": str(result.errors[n.id]),
            })
        else:
            await broadcast(sketch_id, {
                "type": "step_updated",
                "step_id": n.id,
                "image_url": f"/workdir/{sketch_id}/{n.id}.png",
            })
