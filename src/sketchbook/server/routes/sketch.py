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


@router.get("/", response_class=HTMLResponse)
async def index_view(request: Request) -> HTMLResponse:
    """Render the sketch browser index page listing all known sketches."""
    from sketchbook.server.app import list_sketch_infos

    sketches = list_sketch_infos()
    assert _templates is not None
    return _templates.TemplateResponse(request, "index.html", {"sketches": sketches})


@router.get("/sketch/{sketch_id}", response_class=HTMLResponse)
async def sketch_view(request: Request, sketch_id: str) -> HTMLResponse:
    """Render the sketch overview page (DAG + all-step Tweakpane)."""
    from sketchbook.server.app import get_sketch

    sketch = get_sketch(sketch_id)
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
                "input_ids": [src.id for src in sketch.dag.node(nid)._inputs.values()],
            }
            for nid in component
        ]
        for component in components
    ]
    # Flatten for backwards-compat (tests check node IDs appear in response text)
    nodes = [node for group in groups for node in group]

    assert _templates is not None
    return _templates.TemplateResponse(
        request,
        "sketch.html",
        {"sketch_id": sketch_id, "nodes": nodes, "groups": groups},
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
