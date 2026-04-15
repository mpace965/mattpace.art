"""v3 routes — serve @sketch-based pipelines under the /v3/ prefix."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse

from sketchbook.core.protocol import SketchValueProtocol

log = logging.getLogger("sketchbook.server.routes.v3")

router = APIRouter(prefix="/v3")


@router.get("/sketch/{sketch_id}", response_class=HTMLResponse)
async def v3_sketch_view(request: Request, sketch_id: str) -> HTMLResponse:
    """Render a minimal page with one <img> pointing at the first output node."""
    fn_registry = request.app.state.fn_registry
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    if not dag.output_nodes:
        raise HTTPException(
            status_code=404,
            detail=f"Sketch '{sketch_id}' has no output nodes",
        )

    output_step_id, _, _ = dag.output_nodes[0]
    node = dag.nodes.get(output_step_id)
    if node is None:
        raise HTTPException(
            status_code=404,
            detail=f"Output node '{output_step_id}' not found",
        )

    ext = node.output.extension if isinstance(node.output, SketchValueProtocol) else "txt"
    image_url = f"/v3/workdir/{sketch_id}/{output_step_id}.{ext}"

    html = f'<!doctype html><html><body><img src="{image_url}" alt="{sketch_id}"></body></html>'
    return HTMLResponse(html)


@router.get("/workdir/{sketch_id}/{filename}")
async def v3_workdir_file(request: Request, sketch_id: str, filename: str) -> FileResponse:
    """Stream a workdir output file for the given sketch."""
    fn_registry = request.app.state.fn_registry
    file_path: Path = fn_registry.sketches_dir / sketch_id / ".workdir" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return FileResponse(str(file_path))


@router.websocket("/ws/{sketch_id}")
async def v3_ws_endpoint(websocket: WebSocket, sketch_id: str) -> None:
    """Accept a WebSocket connection and push step_updated events on file changes."""
    fn_registry = websocket.app.state.fn_registry

    await websocket.accept()
    fn_registry.connections[sketch_id].add(websocket)
    log.info(f"v3 WebSocket connected for sketch '{sketch_id}'")

    # Push current output state so the browser is up-to-date after reconnect.
    dag = fn_registry.get_dag(sketch_id)
    if dag is not None:
        for node in dag.topo_sort():
            if not isinstance(node.output, SketchValueProtocol):
                continue
            ext = node.output.extension
            workdir = fn_registry.sketches_dir / sketch_id / ".workdir"
            if (workdir / f"{node.step_id}.{ext}").exists():
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "step_updated",
                            "step_id": node.step_id,
                            "image_url": f"/v3/workdir/{sketch_id}/{node.step_id}.{ext}",
                        }
                    )
                )

    try:
        await websocket.receive()
    except WebSocketDisconnect:
        pass
    finally:
        fn_registry.connections[sketch_id].discard(websocket)
        log.info(f"v3 WebSocket disconnected for sketch '{sketch_id}'")
