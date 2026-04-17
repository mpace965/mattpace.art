"""Output bundle builder — build_bundle_fns for v3 @sketch functions.

Building is split into three phases:

  Phase 1 (discovery)  — sequential, cheap: resolve presets and create tasks.
  Phase 2 (execution)  — parallel, expensive: one fresh BuiltDAG per variant.
  Phase 3 (manifest)   — sequential, trivial: assemble and write manifest.json.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("sketchbook.bundle.builder")


def _slug(sketch_id: str) -> str:
    """Convert a sketch ID (snake_case) to a URL slug (kebab-case)."""
    return sketch_id.replace("_", "-")


@dataclass
class _VariantTaskFn:
    """All inputs needed to build one (sketch, preset) variant from a @sketch function."""

    sketch_key: str
    sketch_fn: Callable
    sketch_dir: Path
    presets_dir: Path
    preset_name: str
    sketch_output_dir: Path
    bundle_name: str
    output_node_step_id: str


@dataclass
class _VariantResultFn:
    """Outcome of building one (sketch, preset) variant from a @sketch function."""

    sketch_key: str
    preset_name: str
    ok: bool
    extension: str = field(default="png")


@dataclass
class _DiscoveryResultFn:
    """Discovery output for one @sketch function."""

    meta: dict[str, Any]
    tasks: list[_VariantTaskFn]
    preset_order: list[str]


def _build_variant_fn(task: _VariantTaskFn) -> _VariantResultFn:
    """Execute the full pipeline for one (sketch, preset) pair and save the output image."""
    from sketchbook.core.decorators import SketchContext
    from sketchbook.core.executor import execute_built
    from sketchbook.core.presets import load_preset_into_built
    from sketchbook.core.protocol import SketchValueProtocol
    from sketchbook.core.wiring import wire_sketch

    ctx = SketchContext(mode="build")
    dag = wire_sketch(task.sketch_fn, ctx, task.sketch_dir)
    load_preset_into_built(dag, task.presets_dir, task.preset_name)

    with tempfile.TemporaryDirectory() as tmp:
        result = execute_built(dag, Path(tmp), mode="build")

    if not result.ok:
        log.warning(f"  preset '{task.preset_name}' failed: {result.errors}")
        return _VariantResultFn(task.sketch_key, task.preset_name, ok=False)

    output_node = dag.nodes.get(task.output_node_step_id)
    if output_node is None or output_node.output is None:
        log.warning(f"  output node '{task.output_node_step_id}' has no output after execution")
        return _VariantResultFn(task.sketch_key, task.preset_name, ok=False)

    val = output_node.output
    ext = val.extension if isinstance(val, SketchValueProtocol) else "bin"
    dest = task.sketch_output_dir / f"{task.preset_name}.{ext}"
    dest.write_bytes(val.to_bytes("build"))
    log.info(f"  baked {task.preset_name} -> {dest}")

    return _VariantResultFn(task.sketch_key, task.preset_name, ok=True, extension=ext)


def _discover_sketch_fn(
    sketch_key: str,
    sketch_fn: Callable,
    sketches_dir: Path,
    output_dir: Path,
    bundle_name: str,
) -> _DiscoveryResultFn | None:
    """Resolve the preset list and create variant tasks for one @sketch function.

    Return None if the sketch should be skipped (no matching output nodes, no presets).
    """
    from sketchbook.core.decorators import SketchContext
    from sketchbook.core.presets import list_preset_names
    from sketchbook.core.wiring import wire_sketch

    sketch_dir = sketches_dir / sketch_key
    log.info(f"Processing sketch '{sketch_key}'")

    ctx = SketchContext(mode="build")
    dag = wire_sketch(sketch_fn, ctx, sketch_dir)

    matching = [(sid, bn, presets) for sid, bn, presets in dag.output_nodes if bn == bundle_name]
    if not matching:
        log.info(f"Skipping '{sketch_key}': no output nodes for bundle '{bundle_name}'")
        return None

    if len(matching) > 1:
        log.warning(
            f"  '{sketch_key}' has multiple output nodes for bundle '{bundle_name}'; "
            f"using the first node's presets filter"
        )

    output_step_id, _, node_presets = matching[0]
    presets_dir = sketch_dir / "presets"
    all_presets = list_preset_names(presets_dir)

    if not all_presets:
        log.info(f"Skipping '{sketch_key}': no saved presets")
        return None

    if node_presets is not None:
        presets = [p for p in node_presets if p in all_presets]
        missing = [p for p in node_presets if p not in all_presets]
        if missing:
            log.warning(f"  output() presets references unknown preset(s): {missing}")
    else:
        presets = list(all_presets)

    if not presets:
        log.info(f"Skipping '{sketch_key}': no matching presets after filtering")
        return None

    slug = _slug(sketch_key)
    sketch_output_dir = output_dir / slug
    sketch_output_dir.mkdir(parents=True, exist_ok=True)

    sketch_meta_obj = getattr(sketch_fn, "__sketch_meta__", None)
    meta: dict[str, Any] = {
        "slug": slug,
        "name": sketch_meta_obj.name if sketch_meta_obj else sketch_key,
        "description": sketch_meta_obj.description if sketch_meta_obj else "",
        "date": sketch_meta_obj.date if sketch_meta_obj else "",
    }

    tasks = [
        _VariantTaskFn(
            sketch_key=sketch_key,
            sketch_fn=sketch_fn,
            sketch_dir=sketch_dir,
            presets_dir=presets_dir,
            preset_name=p,
            sketch_output_dir=sketch_output_dir,
            bundle_name=bundle_name,
            output_node_step_id=output_step_id,
        )
        for p in presets
    ]

    return _DiscoveryResultFn(meta=meta, tasks=tasks, preset_order=presets)


def build_bundle_fns(
    sketch_fns: dict[str, Callable],
    sketches_dir: Path,
    output_dir: Path,
    bundle_name: str,
    workers: int | None = None,
) -> None:
    """Build a named output bundle from all @sketch functions.

    Phase 1 (discovery): wire each sketch with SketchContext(mode='build'), find output nodes
        matching bundle_name, resolve the preset list, create a _VariantTaskFn per
        (sketch, preset).
    Phase 2 (execution, parallel): for each task — wire a fresh BuiltDAG, load the preset,
        execute in build mode, write the output bytes to output_dir/{slug}/{preset}.{ext}.
    Phase 3 (manifest): assemble per-sketch entries and write manifest.json.

    workers=None uses ThreadPoolExecutor's default (min(32, cpu_count + 4)).
    workers=1 gives sequential behaviour identical to a single-threaded loop.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1: discovery (sequential)
    tasks: list[_VariantTaskFn] = []
    sketch_meta: dict[str, dict[str, Any]] = {}
    preset_order: dict[str, list[str]] = {}

    for sketch_key, sketch_fn in sketch_fns.items():
        discovery = _discover_sketch_fn(
            sketch_key, sketch_fn, sketches_dir, output_dir, bundle_name
        )
        if discovery is None:
            continue
        sketch_meta[sketch_key] = discovery.meta
        preset_order[sketch_key] = discovery.preset_order
        tasks.extend(discovery.tasks)

    # Phase 2: parallel execution
    produced: dict[str, dict[str, str]] = {key: {} for key in sketch_meta}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_build_variant_fn, task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                log.warning(f"  variant '{task.sketch_key}/{task.preset_name}' raised: {exc}")
                continue
            if result.ok:
                produced[result.sketch_key][result.preset_name] = result.extension

    # Phase 3: manifest (sequential)
    entries: list[dict[str, Any]] = []
    for sketch_key, meta in sketch_meta.items():
        preset_ext_map = produced[sketch_key]
        if not preset_ext_map:
            log.warning(f"Skipping '{sketch_key}': all presets failed")
            shutil.rmtree(output_dir / meta["slug"], ignore_errors=True)
            continue
        ordered = [(p, preset_ext_map[p]) for p in preset_order[sketch_key] if p in preset_ext_map]
        entries.append(
            {
                **meta,
                "variants": [
                    {"name": p, "image_path": f"{meta['slug']}/{p}.{ext}"} for p, ext in ordered
                ],
            }
        )

    entries.sort(key=lambda e: e["date"], reverse=True)
    bundle_path = output_dir / "manifest.json"
    bundle_path.write_text(json.dumps(entries, indent=2))
    log.info(f"Wrote {len(entries)} sketch(es) to {bundle_path}")
