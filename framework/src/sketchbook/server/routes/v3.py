"""v3 routes — serve @sketch-based pipelines under the /v3/ prefix."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from sketchbook.core.executor_v3 import execute_partial_built
from sketchbook.core.introspect import coerce_param
from sketchbook.core.protocol import SketchValueProtocol
from sketchbook.server.tweakpane_v3 import built_node_to_tweakpane

log = logging.getLogger("sketchbook.server.routes.v3")

router = APIRouter(prefix="/v3")


@router.get("/sketch/{sketch_id}", response_class=HTMLResponse)
async def v3_sketch_view(request: Request, sketch_id: str) -> HTMLResponse:
    """Render the full sketch UI (DAG cards + Tweakpane) for a v3 @sketch."""
    fn_registry = request.app.state.fn_registry
    templates = request.app.state.templates
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    # Build the groups/nodes context that sketch.html expects.
    nodes_data: list[dict] = []
    for node in dag.topo_sort():
        fn = getattr(node.fn, "__wrapped__", node.fn)
        ext = node.output.extension if isinstance(node.output, SketchValueProtocol) else "txt"
        nodes_data.append(
            {
                "id": node.step_id,
                "type": fn.__name__,
                "depth": 0,  # resolved below
                "input_ids": list(node.source_ids.values()),
                "image_url": f"/v3/workdir/{sketch_id}/{node.step_id}.{ext}",
            }
        )

    # Compute DAG depth per node (longest path from a root).
    depths: dict[str, int] = {}
    for n in nodes_data:
        if not n["input_ids"]:
            depths[n["id"]] = 0
        else:
            depths[n["id"]] = max(depths[iid] for iid in n["input_ids"]) + 1
    for n in nodes_data:
        n["depth"] = depths[n["id"]]

    # v3 pipelines are a single linear chain — one group.
    groups = [nodes_data]

    return templates.TemplateResponse(
        request,
        "sketch.html",
        {
            "sketch_id": sketch_id,
            "nodes": nodes_data,
            "groups": groups,
            "url_prefix": "/v3",
        },
    )


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


@router.get("/api/sketches/{sketch_id}/params")
async def v3_get_all_params(request: Request, sketch_id: str) -> dict[str, Any]:
    """Return Tweakpane schema for every step, keyed by step_id."""
    fn_registry = request.app.state.fn_registry
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    return {node.step_id: built_node_to_tweakpane(node) for node in dag.topo_sort()}


@router.get("/api/sketches/{sketch_id}/params/{step_id}")
async def v3_get_step_params(request: Request, sketch_id: str, step_id: str) -> dict[str, Any]:
    """Return Tweakpane schema for one step's params."""
    fn_registry = request.app.state.fn_registry
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    node = dag.nodes.get(step_id)
    if node is None:
        raise HTTPException(
            status_code=404, detail=f"Step '{step_id}' not found in sketch '{sketch_id}'"
        )
    return built_node_to_tweakpane(node)


class ParamUpdateV3(BaseModel):
    """Request body for a single param update."""

    step_id: str
    param_name: str
    value: float | int | bool | str


@router.patch("/api/sketches/{sketch_id}/params")
async def v3_update_param(request: Request, sketch_id: str, body: ParamUpdateV3) -> dict[str, bool]:
    """Coerce, store, re-execute, and broadcast a param change."""
    fn_registry = request.app.state.fn_registry
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    node = dag.nodes.get(body.step_id)
    if node is None:
        raise HTTPException(
            status_code=404,
            detail=f"Step '{body.step_id}' not found in sketch '{sketch_id}'",
        )
    spec = next((s for s in node.param_schema if s.name == body.param_name), None)
    if spec is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown param '{body.param_name}' on step '{body.step_id}'",
        )

    node.param_values[body.param_name] = coerce_param(spec, body.value)

    sketch_dir = fn_registry.sketches_dir / sketch_id
    workdir = sketch_dir / ".workdir"
    result = execute_partial_built(dag, [body.step_id], workdir)
    await fn_registry.broadcast_results(sketch_id, dag, result)
    return {"ok": True}
