"""Routes — serve @sketch-based pipelines at the root prefix."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from sketchbook.core.introspect import coerce_param
from sketchbook.core.presets import list_preset_names
from sketchbook.core.protocol import SketchValueProtocol, output_kind
from sketchbook.server.tweakpane import built_node_to_tweakpane

log = logging.getLogger("sketchbook.server.routes.sketches")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def sketch_index(request: Request) -> HTMLResponse:
    """Render an index page listing all available sketches."""
    fn_registry = request.app.state.fn_registry
    templates = request.app.state.templates
    sketches = [
        {
            "slug": slug,
            "url": f"/sketch/{slug}",
            "name": fn.__sketch_meta__.name,
            "description": fn.__sketch_meta__.description,
            "date": fn.__sketch_meta__.date,
        }
        for slug, fn in sorted(
            fn_registry.sketch_fns.items(),
            key=lambda kv: kv[1].__sketch_meta__.date,
            reverse=True,
        )
    ]
    return templates.TemplateResponse(
        request,
        "index.html",
        {"sketches": sketches},
    )


@router.get("/sketch/{sketch_id}", response_class=HTMLResponse)
async def sketch_view(request: Request, sketch_id: str) -> HTMLResponse:
    """Render the full sketch UI (DAG cards + Tweakpane) for a @sketch."""
    fn_registry = request.app.state.fn_registry
    templates = request.app.state.templates
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    last_result = fn_registry.get_last_result(sketch_id)
    last_outputs = last_result.outputs if last_result is not None else {}
    depths = dag.node_depths()
    nodes_data: list[dict] = []
    for node in dag.nodes_in_order():
        fn = getattr(node.fn, "__wrapped__", node.fn)
        output = last_outputs.get(node.step_id)
        kind = output_kind(output)
        ext = output.extension if isinstance(output, SketchValueProtocol) else "txt"
        nodes_data.append(
            {
                "id": node.step_id,
                "type": fn.__name__,
                "depth": depths[node.step_id],
                "input_ids": list(node.source_ids.values()),
                "image_url": f"/workdir/{sketch_id}/{node.step_id}.{ext}",
                "kind": kind,
            }
        )

    # Pipelines are a single linear chain — one group.
    groups = [nodes_data]

    return templates.TemplateResponse(
        request,
        "sketch.html",
        {
            "sketch_id": sketch_id,
            "nodes": nodes_data,
            "groups": groups,
            "url_prefix": "",
        },
    )


@router.get("/sketch/{sketch_id}/step/{step_id}", response_class=HTMLResponse)
async def sketch_step_view(request: Request, sketch_id: str, step_id: str) -> HTMLResponse:
    """Render the fullscreen step output view for a @sketch step."""
    fn_registry = request.app.state.fn_registry
    templates = request.app.state.templates
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    node = dag.nodes.get(step_id)
    if node is None:
        raise HTTPException(
            status_code=404,
            detail=f"Step '{step_id}' not found in sketch '{sketch_id}'",
        )
    last_result = fn_registry.get_last_result(sketch_id)
    output = last_result.outputs.get(step_id) if last_result is not None else None
    kind = output_kind(output)
    ext = output.extension if isinstance(output, SketchValueProtocol) else "txt"
    image_url = f"/workdir/{sketch_id}/{step_id}.{ext}"
    return templates.TemplateResponse(
        request,
        "step.html",
        {
            "sketch_id": sketch_id,
            "step_id": step_id,
            "image_url": image_url,
            "kind": kind,
            "url_prefix": "",
        },
    )


@router.get("/workdir/{sketch_id}/{filename}")
async def sketch_workdir_file(request: Request, sketch_id: str, filename: str) -> FileResponse:
    """Stream a workdir output file for the given sketch."""
    fn_registry = request.app.state.fn_registry
    file_path: Path = fn_registry.sketches_dir / sketch_id / ".workdir" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return FileResponse(str(file_path))


@router.websocket("/ws/{sketch_id}")
async def sketch_ws_endpoint(websocket: WebSocket, sketch_id: str) -> None:
    """Accept a WebSocket connection and push step_updated events on file changes."""
    fn_registry = websocket.app.state.fn_registry

    await websocket.accept()
    fn_registry.connections[sketch_id].add(websocket)
    log.info(f"WebSocket connected for sketch '{sketch_id}'")

    dag = fn_registry.get_dag(sketch_id)
    if dag is not None:
        workdir = fn_registry.sketches_dir / sketch_id / ".workdir"
        last_result = fn_registry.get_last_result(sketch_id)
        await fn_registry.dump_initial_state(websocket, sketch_id, dag, workdir, last_result)

    try:
        await websocket.receive()
    except WebSocketDisconnect:
        pass
    finally:
        fn_registry.connections[sketch_id].discard(websocket)
        log.info(f"WebSocket disconnected for sketch '{sketch_id}'")


@router.get("/api/sketches/{sketch_id}/params")
async def get_all_params(request: Request, sketch_id: str) -> dict[str, Any]:
    """Return Tweakpane schema for every step, keyed by step_id."""
    fn_registry = request.app.state.fn_registry
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    return {node.step_id: built_node_to_tweakpane(node) for node in dag.nodes_in_order()}


@router.get("/api/sketches/{sketch_id}/params/{step_id}")
async def get_step_params(request: Request, sketch_id: str, step_id: str) -> dict[str, Any]:
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


class ParamUpdate(BaseModel):
    """Request body for a single param update."""

    step_id: str
    param_name: str
    value: float | int | bool | str


@router.patch("/api/sketches/{sketch_id}/params")
async def update_param(request: Request, sketch_id: str, body: ParamUpdate) -> dict[str, bool]:
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

    coerced = coerce_param(spec, body.value)
    result = fn_registry.set_param(sketch_id, body.step_id, body.param_name, coerced)
    await fn_registry.broadcast_results(sketch_id, dag, result)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Preset routes
# ---------------------------------------------------------------------------


class SavePresetRequest(BaseModel):
    """Request body for POST /api/sketches/{sketch_id}/presets."""

    name: str


@router.get("/api/sketches/{sketch_id}/presets")
async def list_presets(request: Request, sketch_id: str) -> dict[str, Any]:
    """Return named presets and current active state {dirty, based_on}."""
    fn_registry = request.app.state.fn_registry
    if sketch_id not in fn_registry.sketch_fns:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    presets_dir = fn_registry.sketches_dir / sketch_id / "presets"
    dirty, based_on = fn_registry.get_preset_state(sketch_id)
    return {
        "presets": list_preset_names(presets_dir),
        "active": {"dirty": dirty, "based_on": based_on},
    }


@router.post("/api/sketches/{sketch_id}/presets")
async def save_preset(request: Request, sketch_id: str, body: SavePresetRequest) -> dict[str, Any]:
    """Save current param values as a named preset.

    Does not re-execute or broadcast — saving is pure persistence on already-applied values.
    """
    fn_registry = request.app.state.fn_registry
    if fn_registry.get_dag(sketch_id) is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    fn_registry.save_preset(sketch_id, body.name)
    log.info(f"Saved preset '{body.name}' for sketch '{sketch_id}'")
    return {"ok": True, "name": body.name}


@router.post("/api/sketches/{sketch_id}/presets/new")
async def new_preset(request: Request, sketch_id: str) -> dict[str, Any]:
    """Reset all params to defaults, re-execute, and broadcast."""
    fn_registry = request.app.state.fn_registry
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    result = fn_registry.reset_to_defaults_and_execute(sketch_id)
    await fn_registry.broadcast_results(sketch_id, dag, result)
    await fn_registry.broadcast(sketch_id, {"type": "preset_state"})
    log.info(f"Reset to defaults for sketch '{sketch_id}'")
    return {"ok": True}


@router.post("/api/sketches/{sketch_id}/presets/{name}/load")
async def load_preset(request: Request, sketch_id: str, name: str) -> dict[str, Any]:
    """Load a named preset, re-execute, and broadcast step_updated."""
    fn_registry = request.app.state.fn_registry
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    try:
        result = fn_registry.load_preset_and_execute(sketch_id, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await fn_registry.broadcast_results(sketch_id, dag, result)
    await fn_registry.broadcast(sketch_id, {"type": "preset_state"})
    log.info(f"Loaded preset '{name}' for sketch '{sketch_id}'")
    return {"ok": True}
