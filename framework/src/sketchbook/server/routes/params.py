"""Param schema and update API routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sketchbook.core.executor import execute
from sketchbook.server.deps import get_registry
from sketchbook.server.registry import SketchRegistry
from sketchbook.server.tweakpane import param_registry_to_tweakpane

log = logging.getLogger("sketchbook.server.routes.params")

router = APIRouter()


class ParamUpdate(BaseModel):
    """Request body for PATCH /api/sketches/{sketch_id}/params."""

    step_id: str
    param_name: str
    value: float | int | bool | str


@router.get("/api/sketches/{sketch_id}/params")
async def get_all_params(sketch_id: str, registry: SketchRegistry = Depends(get_registry)):
    """Return param schema + current values for all steps in the sketch."""
    sketch = registry.get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    return {
        node.id: param_registry_to_tweakpane(node.step.param_registry)
        for node in sketch.dag.topo_sort()
    }


@router.get("/api/sketches/{sketch_id}/params/{step_id}")
async def get_step_params(
    sketch_id: str,
    step_id: str,
    registry: SketchRegistry = Depends(get_registry),
):
    """Return param schema + current values for a single step."""
    sketch = registry.get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    try:
        node = sketch.dag.node(step_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Step '{step_id}' not found in sketch '{sketch_id}'",
        )

    return {"params": param_registry_to_tweakpane(node.step.param_registry)}


@router.patch("/api/sketches/{sketch_id}/params")
async def update_param(
    sketch_id: str,
    body: ParamUpdate,
    registry: SketchRegistry = Depends(get_registry),
):
    """Update a single param value, re-execute the pipeline, and broadcast updates."""
    sketch = registry.get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    try:
        node = sketch.dag.node(body.step_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Step '{body.step_id}' not found in sketch '{sketch_id}'",
        )

    try:
        node.step.set_param(body.param_name, body.value)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    log.info(
        f"Param updated: sketch='{sketch_id}' step='{body.step_id}' {body.param_name}={body.value}"
    )

    sketch.preset_manager.mark_dirty()
    sketch.preset_manager.save_active(sketch.dag)

    result = execute(sketch.dag)
    await registry.broadcast_results(sketch_id, sketch.dag, result)
    await registry.broadcast_preset_state(sketch_id, sketch.preset_manager)
    return {"ok": True}
