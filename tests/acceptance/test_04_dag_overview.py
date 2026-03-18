"""Acceptance test 04: DAG Overview and Multi-Step Pipelines.

Acceptance criteria:
    A sketch with source → blur → edge detect has a /api/sketches/{id}/dag endpoint
    that returns the correct nodes and edges.
    GET /sketch/{sketch_id} renders a page that links to all step views.
    GET /api/sketches/{sketch_id}/params returns params for all steps.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_dag_endpoint_reflects_pipeline_structure(
    tmp_portrait_sketch: Path, portrait_test_client: TestClient
) -> None:
    """The DAG endpoint returns the correct graph for a multi-step pipeline."""
    resp = portrait_test_client.get("/api/sketches/edge_portrait/dag")
    assert resp.status_code == 200
    dag = resp.json()

    node_ids = {n["id"] for n in dag["nodes"]}
    assert "source_photo" in node_ids
    assert "gaussian_blur_0" in node_ids
    assert "edge_detect_0" in node_ids

    edges = {(e["from"], e["to"]) for e in dag["edges"]}
    assert ("source_photo", "gaussian_blur_0") in edges
    assert ("gaussian_blur_0", "edge_detect_0") in edges


def test_sketch_page_renders_all_steps(
    tmp_portrait_sketch: Path, portrait_test_client: TestClient
) -> None:
    """The sketch overview page contains links to all step views."""
    response = portrait_test_client.get("/sketch/edge_portrait")
    assert response.status_code == 200
    assert "gaussian_blur_0" in response.text
    assert "edge_detect_0" in response.text


def test_all_step_params_in_sketch_view(
    tmp_portrait_sketch: Path, portrait_test_client: TestClient
) -> None:
    """The full params endpoint returns params for all steps."""
    resp = portrait_test_client.get("/api/sketches/edge_portrait/params")
    assert resp.status_code == 200
    params = resp.json()
    assert "gaussian_blur_0" in params
    assert "edge_detect_0" in params
