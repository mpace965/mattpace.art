"""Sketch and step view routes."""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

log = logging.getLogger("sketchbook.server.routes.sketch")

router = APIRouter()
_templates: Jinja2Templates | None = None


def init_templates(templates: Jinja2Templates) -> None:
    """Inject the Jinja2Templates instance."""
    global _templates
    _templates = templates


@router.get("/sketch/{sketch_id}", response_class=HTMLResponse)
async def sketch_view(request: Request, sketch_id: str) -> HTMLResponse:
    """Render the sketch overview page (DAG + all-step Tweakpane)."""
    from sketchbook.server.app import get_sketch

    sketch = get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    nodes = [
        {"id": node.id, "type": type(node.step).__name__}
        for node in sketch.dag.topo_sort()
    ]

    assert _templates is not None
    return _templates.TemplateResponse(
        request,
        "sketch.html",
        {"sketch_id": sketch_id, "nodes": nodes},
    )


@router.get("/sketch/{sketch_id}/step/{step_id}", response_class=HTMLResponse)
async def step_view(request: Request, sketch_id: str, step_id: str) -> HTMLResponse:
    """Render the fullscreen step output view."""
    from sketchbook.server.app import get_sketch

    sketch = get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    try:
        node = sketch.dag.node(step_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Step '{step_id}' not found in sketch '{sketch_id}'")

    image_url = f"/workdir/{sketch_id}/{step_id}.png"

    assert _templates is not None
    return _templates.TemplateResponse(
        request,
        "step.html",
        {"sketch_id": sketch_id, "step_id": step_id, "image_url": image_url},
    )
