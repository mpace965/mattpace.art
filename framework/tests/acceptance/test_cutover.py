# tests/acceptance/test_cutover.py

from __future__ import annotations

import json
from pathlib import Path

from sketchbook.bundle.builder import build_bundle_fns
from sketchbook.discovery import discover_sketch_fns

_FRAMEWORK_SRC = Path(__file__).parent.parent.parent / "src" / "sketchbook"
_SKETCHES_DIR = Path(__file__).parent.parent.parent.parent / "sketches"

_FORBIDDEN_SYMBOLS = {
    "PipelineStep",
    "from sketchbook.core.sketch",
    "DAGNode",
    "from sketchbook.core.dag",
}


def test_no_old_framework_symbols():
    """The framework source contains no references to old API symbols."""
    violations: list[str] = []
    for py_file in _FRAMEWORK_SRC.rglob("*.py"):
        text = py_file.read_text()
        for term in _FORBIDDEN_SYMBOLS:
            if term in text:
                violations.append(f"{py_file}: found '{term}'")
    assert not violations, "\n".join(violations)


def test_all_sketches_load_in_dev_server(fn_registry_client_real):
    """All four real sketches wire and serve without error via the root-prefixed routes."""
    for slug in ["cardboard", "cardboard_stripes", "fence-torn-paper", "kick-polygons"]:
        response = fn_registry_client_real.get(f"/sketch/{slug}")
        assert response.status_code == 200, f"Sketch '{slug}' failed: {response.text}"


def test_build_produces_valid_site(tmp_path):
    """build_bundle_fns discovers all four ported sketches and writes a valid manifest."""
    sketch_fns = discover_sketch_fns(_SKETCHES_DIR)
    assert len(sketch_fns) >= 4, f"Expected >= 4 sketch functions, got: {list(sketch_fns)}"

    build_bundle_fns(sketch_fns, _SKETCHES_DIR, tmp_path, "bundle", workers=1)

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    slugs = {e["slug"] for e in manifest}
    assert "cardboard" in slugs
    assert "cardboard-stripes" in slugs
    assert "kick-polygons" in slugs
