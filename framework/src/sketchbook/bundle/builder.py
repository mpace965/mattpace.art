"""Output bundle builder.

Discovers OutputBundle nodes in each sketch, iterates saved presets, bakes
variant images, and writes a JSON bundle file to the output directory.

Building is split into three phases:

  Phase 1 (discovery)  — sequential, cheap: resolve presets and create tasks.
  Phase 2 (execution)  — parallel, expensive: one fresh Sketch per variant.
  Phase 3 (manifest)   — sequential, trivial: assemble and write manifest.json.
"""

from __future__ import annotations

import json
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sketchbook.core.executor import execute
from sketchbook.core.sketch import Sketch
from sketchbook.steps.output_bundle import OutputBundle

log = logging.getLogger("sketchbook.bundle.builder")


def _slug(sketch_id: str) -> str:
    """Convert a sketch ID (snake_case) to a URL slug (kebab-case)."""
    return sketch_id.replace("_", "-")


@dataclass
class _VariantTask:
    sketch_id: str
    sketch_cls: type[Sketch]
    sketch_dir: Path
    preset_name: str
    sketch_output_dir: Path
    bundle_name: str


@dataclass
class _VariantResult:
    sketch_id: str
    preset_name: str
    ok: bool


@dataclass
class _DiscoveryResult:
    meta: dict[str, Any]
    tasks: list[_VariantTask]
    preset_order: list[str]


def _build_variant(task: _VariantTask) -> _VariantResult:
    """Execute the full pipeline for one (sketch, preset) pair and save the output image."""
    sketch = task.sketch_cls(task.sketch_dir, mode="build")
    bundle_nodes = [
        n
        for n in sketch.dag.topo_sort()
        if isinstance(n.step, OutputBundle) and n.step.bundle_name == task.bundle_name
    ]
    sketch.preset_manager.load_preset(task.preset_name, sketch.dag, save=False)
    result = execute(sketch.dag)
    if not result.ok:
        log.warning(f"  preset '{task.preset_name}' failed: {result.errors}")
        return _VariantResult(task.sketch_id, task.preset_name, ok=False)

    for bundle_node in bundle_nodes:
        if bundle_node.output is not None:
            dest = task.sketch_output_dir / f"{task.preset_name}.png"
            dest.write_bytes(bundle_node.output.to_bytes())
            log.info(f"  baked {task.preset_name} -> {dest}")

    return _VariantResult(task.sketch_id, task.preset_name, ok=True)


def _discover_sketch(
    sketch_id: str,
    sketch_cls: type[Sketch],
    sketches_dir: Path,
    output_dir: Path,
    bundle_name: str,
) -> _DiscoveryResult | None:
    """Instantiate a sketch to read its config and resolve the preset list.

    Return a _DiscoveryResult with metadata and variant tasks, or None if the sketch
    should be skipped. The discovery instance is discarded after this function returns.
    """
    sketch_dir = sketches_dir / sketch_id
    log.info(f"Processing sketch '{sketch_id}'")

    sketch = sketch_cls(sketch_dir, mode="build")

    bundle_nodes = [
        n
        for n in sketch.dag.topo_sort()
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

    tasks = [
        _VariantTask(
            sketch_id=sketch_id,
            sketch_cls=sketch_cls,
            sketch_dir=sketch_dir,
            preset_name=preset_name,
            sketch_output_dir=sketch_output_dir,
            bundle_name=bundle_name,
        )
        for preset_name in presets
    ]

    meta: dict[str, Any] = {
        "slug": slug,
        "name": sketch.name,
        "description": sketch.description,
        "date": sketch.date,
    }

    return _DiscoveryResult(meta=meta, tasks=tasks, preset_order=presets)


def build_bundle(
    sketch_classes: dict[str, type[Sketch]],
    sketches_dir: Path,
    output_dir: Path,
    bundle_name: str,
    workers: int | None = None,
) -> None:
    """Build a named output bundle from all sketches that have matching OutputBundle nodes.

    Phase 1 (discovery): for each sketch, resolve the preset list and create variant tasks.
    Phase 2 (execution): run each variant task in a thread pool.
    Phase 3 (manifest): assemble results into per-sketch entries and write manifest.json.

    workers=None uses ThreadPoolExecutor's default (min(32, cpu_count + 4)).
    workers=1 gives sequential behaviour identical to the old implementation.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1: discovery (sequential)
    tasks: list[_VariantTask] = []
    sketch_meta: dict[str, dict[str, Any]] = {}
    preset_order: dict[str, list[str]] = {}

    for sketch_id, sketch_cls in sketch_classes.items():
        discovery = _discover_sketch(sketch_id, sketch_cls, sketches_dir, output_dir, bundle_name)
        if discovery is None:
            continue
        sketch_meta[sketch_id] = discovery.meta
        preset_order[sketch_id] = discovery.preset_order
        tasks.extend(discovery.tasks)

    # Phase 2: parallel execution
    produced: dict[str, list[str]] = {sid: [] for sid in sketch_meta}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_build_variant, task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                log.warning(f"  variant '{task.sketch_id}/{task.preset_name}' raised: {exc}")
                continue
            if result.ok:
                produced[result.sketch_id].append(result.preset_name)

    # Phase 3: manifest (sequential)
    entries: list[dict[str, Any]] = []
    for sketch_id, meta in sketch_meta.items():
        variants = produced[sketch_id]
        if not variants:
            log.warning(f"Skipping '{sketch_id}': all presets failed")
            shutil.rmtree(output_dir / meta["slug"], ignore_errors=True)
            continue
        # Restore discovery order (produced list is completion-order)
        ordered = [p for p in preset_order[sketch_id] if p in set(variants)]
        entries.append(
            {
                **meta,
                "variants": [{"name": p, "image_path": f"{meta['slug']}/{p}.png"} for p in ordered],
            }
        )

    entries.sort(key=lambda e: e["date"], reverse=True)
    bundle_path = output_dir / "manifest.json"
    bundle_path.write_text(json.dumps(entries, indent=2))
    log.info(f"Wrote {len(entries)} sketch(es) to {bundle_path}")
