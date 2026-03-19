"""WebSocket endpoint for live step updates."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger("sketchbook.server.ws")

router = APIRouter()


@router.websocket("/ws/{sketch_id}")
async def ws_endpoint(websocket: WebSocket, sketch_id: str) -> None:
    """Accept a WebSocket connection, push current state, then hold open for push updates."""
    registry = websocket.app.state.registry

    await websocket.accept()
    registry.connections[sketch_id].add(websocket)
    log.info(f"WebSocket connected for sketch '{sketch_id}'")

    # Push current output state so the browser is up-to-date immediately after
    # reconnecting (e.g. following a server hot-reload).
    sketch = registry.get_sketch(sketch_id)
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
        registry.connections[sketch_id].discard(websocket)
        log.info(f"WebSocket disconnected for sketch '{sketch_id}'")
