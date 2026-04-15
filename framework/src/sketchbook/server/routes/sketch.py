"""Sketch and step view routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from sketchbook.server.deps import get_registry, get_templates
from sketchbook.server.registry import SketchRegistry

log = logging.getLogger("sketchbook.server.routes.sketch")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index_view(
    request: Request,
    registry: SketchRegistry = Depends(get_registry),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Render the sketch browser index page listing all known sketches."""
    sketches = [{**info, "url": f"/sketch/{info['id']}"} for info in registry.list_sketch_infos()]

    fn_registry = getattr(request.app.state, "fn_registry", None)
    if fn_registry is not None:
        for sketch_id, fn in fn_registry.sketch_fns.items():
            meta = getattr(fn, "__sketch_meta__", None)
            sketches.append(
                {
                    "id": sketch_id,
                    "name": getattr(meta, "name", sketch_id),
                    "description": getattr(meta, "description", ""),
                    "date": getattr(meta, "date", ""),
                    "url": f"/v3/sketch/{sketch_id}",
                }
            )

    sketches.sort(key=lambda s: s["date"], reverse=True)
    return templates.TemplateResponse(request, "index.html", {"sketches": sketches})


@router.get("/sketch/{sketch_id}", response_class=HTMLResponse)
async def sketch_view(
    request: Request,
    sketch_id: str,
    registry: SketchRegistry = Depends(get_registry),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Render the sketch overview page (DAG + all-step Tweakpane)."""
    sketch = registry.get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    depths = sketch.dag.node_depths()
    components = sketch.dag.connected_components()
    groups = [
        [
            {
                "id": nid,
                "type": type(sketch.dag.node(nid).step).__name__,
                "depth": depths[nid],
                "input_ids": [src.id for src in sketch.dag.node(nid).source_nodes.values()],
                "image_url": f"/workdir/{sketch_id}/{nid}.png",
            }
            for nid in component
        ]
        for component in components
    ]
    # Flatten for backwards-compat (tests check node IDs appear in response text)
    nodes = [node for group in groups for node in group]

    return templates.TemplateResponse(
        request,
        "sketch.html",
        {"sketch_id": sketch_id, "nodes": nodes, "groups": groups},
    )


@router.get("/sketch/{sketch_id}/step/{step_id}", response_class=HTMLResponse)
async def step_view(
    request: Request,
    sketch_id: str,
    step_id: str,
    registry: SketchRegistry = Depends(get_registry),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Render the fullscreen step output view."""
    sketch = registry.get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    try:
        sketch.dag.node(step_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Step '{step_id}' not found in sketch '{sketch_id}'",
        )

    image_url = f"/workdir/{sketch_id}/{step_id}.png"

    return templates.TemplateResponse(
        request,
        "step.html",
        {"sketch_id": sketch_id, "step_id": step_id, "image_url": image_url},
    )
