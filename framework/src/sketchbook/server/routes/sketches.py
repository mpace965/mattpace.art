"""Routes — serve @sketch-based pipelines at the root prefix."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from sketchbook.core.executor import execute_built
from sketchbook.core.introspect import coerce_param
from sketchbook.core.presets import (
    load_preset_into_built,
    save_active_from_built,
    save_preset_from_built,
)
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

    # Build the groups/nodes context that sketch.html expects.
    nodes_data: list[dict] = []
    for node in dag.topo_sort():
        fn = getattr(node.fn, "__wrapped__", node.fn)
        kind = output_kind(node.output)
        ext = node.output.extension if isinstance(node.output, SketchValueProtocol) else "txt"
        nodes_data.append(
            {
                "id": node.step_id,
                "type": fn.__name__,
                "depth": 0,  # resolved below
                "input_ids": list(node.source_ids.values()),
                "image_url": f"/workdir/{sketch_id}/{node.step_id}.{ext}",
                "kind": kind,
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
    kind = output_kind(node.output)
    ext = node.output.extension if isinstance(node.output, SketchValueProtocol) else "txt"
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

    # Push current output state so the browser is up-to-date after reconnect.
    dag = fn_registry.get_dag(sketch_id)
    if dag is not None:
        workdir = fn_registry.sketches_dir / sketch_id / ".workdir"
        for node in dag.topo_sort():
            if node.output is None:
                continue
            kind = output_kind(node.output)
            ext = node.output.extension if isinstance(node.output, SketchValueProtocol) else "txt"
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
    return {node.step_id: built_node_to_tweakpane(node) for node in dag.topo_sort()}


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


def _list_preset_names(presets_dir: Path) -> list[str]:
    """Return sorted named preset names from presets_dir (excluding _active)."""
    if not presets_dir.exists():
        return []
    return sorted(p.stem for p in presets_dir.glob("*.json") if p.stem != "_active")


@router.get("/api/sketches/{sketch_id}/presets")
async def list_presets(request: Request, sketch_id: str) -> dict[str, Any]:
    """Return named presets and current active state {dirty, based_on}."""
    fn_registry = request.app.state.fn_registry
    if sketch_id not in fn_registry.sketch_fns:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    presets_dir = fn_registry.sketches_dir / sketch_id / "presets"
    return {
        "presets": _list_preset_names(presets_dir),
        "active": {
            "dirty": fn_registry._dirty.get(sketch_id, False),
            "based_on": fn_registry._based_on.get(sketch_id),
        },
    }


@router.post("/api/sketches/{sketch_id}/presets")
async def save_preset(request: Request, sketch_id: str, body: SavePresetRequest) -> dict[str, Any]:
    """Save current param values as a named preset."""
    fn_registry = request.app.state.fn_registry
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    presets_dir = fn_registry.sketches_dir / sketch_id / "presets"
    save_preset_from_built(dag, presets_dir, body.name)
    fn_registry._dirty[sketch_id] = False
    fn_registry._based_on[sketch_id] = body.name
    save_active_from_built(dag, presets_dir, dirty=False, based_on=body.name)
    log.info(f"Saved preset '{body.name}' for sketch '{sketch_id}'")
    return {"ok": True, "name": body.name}


@router.post("/api/sketches/{sketch_id}/presets/new")
async def new_preset(request: Request, sketch_id: str) -> dict[str, Any]:
    """Reset all params to defaults, re-execute, and broadcast."""
    fn_registry = request.app.state.fn_registry
    dag = fn_registry.get_dag(sketch_id)
    if dag is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")
    presets_dir = fn_registry.sketches_dir / sketch_id / "presets"
    workdir = fn_registry.sketches_dir / sketch_id / ".workdir"
    with fn_registry._exec_locks[sketch_id]:
        for node in dag.topo_sort():
            for spec in node.param_schema:
                node.param_values[spec.name] = spec.default
        fn_registry._dirty[sketch_id] = False
        fn_registry._based_on[sketch_id] = None
        save_active_from_built(dag, presets_dir, dirty=False, based_on=None)
        result = execute_built(dag, workdir)
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
    presets_dir = fn_registry.sketches_dir / sketch_id / "presets"
    workdir = fn_registry.sketches_dir / sketch_id / ".workdir"
    try:
        with fn_registry._exec_locks[sketch_id]:
            load_preset_into_built(dag, presets_dir, name)
            fn_registry._dirty[sketch_id] = False
            fn_registry._based_on[sketch_id] = name
            save_active_from_built(dag, presets_dir, dirty=False, based_on=name)
            result = execute_built(dag, workdir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await fn_registry.broadcast_results(sketch_id, dag, result)
    await fn_registry.broadcast(sketch_id, {"type": "preset_state"})
    log.info(f"Loaded preset '{name}' for sketch '{sketch_id}'")
    return {"ok": True}
