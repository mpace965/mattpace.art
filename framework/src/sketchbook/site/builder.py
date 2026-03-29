"""Output bundle builder.

Discovers OutputBundle nodes in each sketch, iterates saved presets, bakes
variant images, and writes a JSON bundle file to the output directory.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from sketchbook.core.executor import execute
from sketchbook.core.sketch import Sketch
from sketchbook.steps.output_bundle import OutputBundle

log = logging.getLogger("sketchbook.site.builder")


def _slug(sketch_id: str) -> str:
    """Convert a sketch ID (snake_case) to a URL slug (kebab-case)."""
    return sketch_id.replace("_", "-")


def _snapshot_variants(
    sketch: Sketch,
    presets: list[str],
    bundle_nodes: list[Any],
    sketch_output_dir: Path,
) -> list[str]:
    """Execute the pipeline for each preset and save OutputBundle images.

    Return the list of preset names that were successfully baked.
    """
    produced: list[str] = []
    for preset_name in presets:
        sketch.preset_manager.load_preset(preset_name, sketch.dag)
        result = execute(sketch.dag)
        if not result.ok:
            log.warning(f"  preset '{preset_name}' failed: {result.errors}")
            continue

        for bundle_node in bundle_nodes:
            if bundle_node.output is not None:
                dest = sketch_output_dir / f"{preset_name}.png"
                dest.write_bytes(bundle_node.output.to_bytes())
                log.info(f"  baked {preset_name} -> {dest}")

        produced.append(preset_name)
    return produced


def _build_sketch(
    sketch_id: str,
    sketch_cls: type[Sketch],
    sketches_dir: Path,
    output_dir: Path,
    bundle_name: str,
) -> dict[str, Any] | None:
    """Build one sketch: bake variants and return its bundle entry dict.

    Return a bundle entry dict on success, or None if the sketch should be skipped.
    """
    sketch_dir = sketches_dir / sketch_id
    log.info(f"Processing sketch '{sketch_id}'")

    sketch = sketch_cls(sketch_dir)

    bundle_nodes = [
        n for n in sketch.dag.topo_sort()
        if isinstance(n.step, OutputBundle) and n.step.bundle_name == bundle_name
    ]
    if not bundle_nodes:
        log.info(f"Skipping '{sketch_id}': no OutputBundle node for bundle '{bundle_name}'")
        return None

    if len(bundle_nodes) > 1:
        log.warning(
            f"  '{sketch_id}' has multiple OutputBundle nodes for bundle '{bundle_name}'; "
            f"using the first node's presets filter"
        )

    all_presets = sketch.preset_manager.list_presets()
    if not all_presets:
        log.info(f"Skipping '{sketch_id}': no saved presets")
        return None

    node_presets = bundle_nodes[0].step.presets
    if node_presets is not None:
        presets = [p for p in node_presets if p in all_presets]
        missing = [p for p in node_presets if p not in all_presets]
        if missing:
            log.warning(f"  OutputBundle.presets references unknown preset(s): {missing}")
    else:
        presets = all_presets

    if not presets:
        log.info(f"Skipping '{sketch_id}': no matching presets after filtering")
        return None

    slug = _slug(sketch_id)
    sketch_output_dir = output_dir / slug
    sketch_output_dir.mkdir(parents=True, exist_ok=True)

    produced = _snapshot_variants(sketch, presets, bundle_nodes, sketch_output_dir)

    if not produced:
        log.warning(f"Skipping '{sketch_id}': all presets failed")
        shutil.rmtree(sketch_output_dir)
        return None

    log.info(f"Built '{sketch_id}' with {len(produced)} variant(s)")
    return {
        "slug": slug,
        "name": sketch.name,
        "description": sketch.description,
        "date": sketch.date,
        "variants": [
            {"name": preset, "image_path": f"{slug}/{preset}.png"}
            for preset in produced
        ],
    }


def build_bundle(
    sketch_classes: dict[str, type[Sketch]],
    sketches_dir: Path,
    output_dir: Path,
    bundle_name: str,
) -> None:
    """Build a named output bundle from all sketches that have matching OutputBundle nodes.

    For each qualifying sketch, iterates saved presets, executes the full pipeline,
    and copies the OutputBundle node's image to <output_dir>/<slug>/<preset>.png.
    Writes the accumulated entries as a JSON array to <output_dir>/<bundle_name>.json.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []

    for sketch_id, sketch_cls in sketch_classes.items():
        entry = _build_sketch(sketch_id, sketch_cls, sketches_dir, output_dir, bundle_name)
        if entry is not None:
            entries.append(entry)

    entries.sort(key=lambda e: e["date"], reverse=True)

    bundle_path = output_dir / "manifest.json"
    bundle_path.write_text(json.dumps(entries, indent=2))
    log.info(f"Wrote {len(entries)} sketch(es) to {bundle_path}")
