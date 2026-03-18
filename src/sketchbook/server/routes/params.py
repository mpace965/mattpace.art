"""Param schema and update API routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sketchbook.server.routes import ws as ws_routes

log = logging.getLogger("sketchbook.server.routes.params")

router = APIRouter()


class ParamUpdate(BaseModel):
    """Request body for PATCH /api/sketches/{sketch_id}/params."""

    step_id: str
    param_name: str
    value: float | int | bool | str


@router.get("/api/sketches/{sketch_id}/params")
async def get_all_params(sketch_id: str):
    """Return param schema + current values for all steps in the sketch."""
    from sketchbook.server.app import get_sketch

    sketch = get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    return {
        node.id: node.step._param_registry.to_schema_dict()
        for node in sketch.dag.topo_sort()
    }


@router.get("/api/sketches/{sketch_id}/params/{step_id}")
async def get_step_params(sketch_id: str, step_id: str):
    """Return param schema + current values for a single step."""
    from sketchbook.server.app import get_sketch

    sketch = get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    try:
        node = sketch.dag.node(step_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Step '{step_id}' not found in sketch '{sketch_id}'")

    return {"params": node.step._param_registry.to_schema_dict()}


@router.patch("/api/sketches/{sketch_id}/params")
async def update_param(sketch_id: str, body: ParamUpdate):
    """Update a single param value, re-execute the pipeline, and broadcast updates."""
    from sketchbook.core.executor import execute
    from sketchbook.server.app import get_sketch

    sketch = get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    try:
        node = sketch.dag.node(body.step_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Step '{body.step_id}' not found in sketch '{sketch_id}'")

    try:
        node.step._param_registry.set_value(body.param_name, body.value)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    log.info(f"Param updated: sketch='{sketch_id}' step='{body.step_id}' {body.param_name}={body.value}")

    sketch.preset_manager.mark_dirty()
    sketch.preset_manager.save_active(sketch.dag)

    result = execute(sketch.dag)
    await ws_routes.broadcast_results(sketch_id, sketch.dag, result)
    await ws_routes.broadcast_preset_state(sketch_id, sketch.preset_manager)
    return {"ok": True}
