"""DAG structure API route."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

log = logging.getLogger("sketchbook.server.routes.dag")

router = APIRouter()


@router.get("/api/sketches/{sketch_id}/dag")
async def get_dag(sketch_id: str):
    """Return the DAG structure as JSON (nodes and edges)."""
    from sketchbook.server.app import get_sketch

    sketch = get_sketch(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{sketch_id}' not found")

    nodes = [
        {"id": node.id, "type": type(node.step).__name__}
        for node in sketch.dag.topo_sort()
    ]
    edges = [
        {"from": from_id, "to": to_id, "input": input_name}
        for from_id, to_id, input_name in sketch.dag.edges
    ]
    return {"nodes": nodes, "edges": edges}
