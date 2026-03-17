"""Preset CRUD API routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger("sketchbook.server.routes.presets")

router = APIRouter()


class SavePresetRequest(BaseModel):
    """Request body for POST /api/sketches/{sketch_id}/presets."""

    name: str


@router.get("/api/sketches/{sketch_id}/presets")
async def list_presets(sketch_id: str):
    """Return all named presets and the current active state."""
    from sketchbook.server.app import get_sketch

    sketch = get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    pm = sketch.preset_manager
    return {
        "presets": pm.list_presets(),
        "active": {
            "dirty": pm.dirty,
            "based_on": pm.based_on,
        },
    }


@router.post("/api/sketches/{sketch_id}/presets")
async def save_preset(sketch_id: str, body: SavePresetRequest):
    """Save the current params as a named preset."""
    from sketchbook.server.app import get_sketch

    sketch = get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    from sketchbook.server.routes import ws as ws_routes

    sketch.preset_manager.save_preset(body.name, sketch.dag)
    log.info(f"Saved preset '{body.name}' for sketch '{sketch_id}'")
    await ws_routes.broadcast_preset_state(sketch_id, sketch.preset_manager)
    return {"ok": True, "name": body.name}


@router.post("/api/sketches/{sketch_id}/presets/new")
async def new_preset(sketch_id: str):
    """Reset all params to defaults and clear the active preset state."""
    from sketchbook.core.executor import execute
    from sketchbook.server.app import get_sketch
    from sketchbook.server.routes import ws as ws_routes

    sketch = get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    sketch.preset_manager.reset(sketch.dag)
    log.info(f"Reset to defaults for sketch '{sketch_id}'")
    result = execute(sketch.dag)
    await ws_routes.broadcast_results(sketch_id, sketch.dag, result)
    await ws_routes.broadcast_preset_state(sketch_id, sketch.preset_manager)
    return {"ok": True}


@router.post("/api/sketches/{sketch_id}/presets/{name}/load")
async def load_preset(sketch_id: str, name: str):
    """Load a named preset, re-execute the pipeline, and broadcast updates."""
    from sketchbook.core.executor import execute
    from sketchbook.server.app import get_sketch
    from sketchbook.server.routes import ws as ws_routes

    sketch = get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    try:
        sketch.preset_manager.load_preset(name, sketch.dag)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    log.info(f"Loaded preset '{name}' for sketch '{sketch_id}'")
    result = execute(sketch.dag)
    await ws_routes.broadcast_results(sketch_id, sketch.dag, result)
    await ws_routes.broadcast_preset_state(sketch_id, sketch.preset_manager)
    return {"ok": True}
