# Plan: Parallel variant building

## What and why

`build_bundle` currently builds every (sketch, preset) combination sequentially.
Each combination is independent — different preset files, different DAG instances,
different output paths. The CPU work (image processing via OpenCV) dominates build
time and OpenCV releases the GIL, so threading gives real concurrency.

The natural unit of parallelism is the **variant**: one (sketch, preset) pair.
Per-sketch parallelism is coarser and leaves speedup on the table when one sketch
has many presets and another has one.

## Current design

```
build_bundle(sketch_classes, ...)
  for sketch_id, sketch_cls:
    sketch = sketch_cls(sketch_dir)          # one instance for the whole sketch
    for preset_name in presets:
      sketch.preset_manager.load_preset(...)  # mutates sketch.dag in place
      execute(sketch.dag)                     # mutates node outputs in place
      save output image
```

The problem: `load_preset` + `execute` mutate a shared `Sketch` instance.
Two presets cannot run concurrently on the same instance.

## Revised design

Split building into two phases:

**Phase 1 — discovery (sequential, cheap):** For each sketch, instantiate one
`Sketch` to read bundle node config and resolve the preset list. Produce a flat
list of `_VariantTask` records. Discard the discovery instance.

**Phase 2 — execution (parallel, expensive):** Each `_VariantTask` is an
independent unit: instantiate a fresh `Sketch`, load one preset, execute the
full DAG, save one image. Submit all tasks to a `ThreadPoolExecutor`. Collect
results as futures complete.

**Phase 3 — manifest (sequential, trivial):** Assemble results into per-sketch
entries, sort by date, write `manifest.json`.

## Data structures

```python
@dataclass
class _VariantTask:
    sketch_id: str
    sketch_cls: type[Sketch]
    sketch_dir: Path
    preset_name: str
    sketch_output_dir: Path
    bundle_name: str
```

```python
@dataclass
class _VariantResult:
    sketch_id: str
    preset_name: str
    ok: bool          # False if execution failed or no output produced
```

## New function: `_build_variant`

```python
def _build_variant(task: _VariantTask) -> _VariantResult:
    sketch = task.sketch_cls(task.sketch_dir)
    bundle_nodes = [
        n for n in sketch.dag.topo_sort()
        if isinstance(n.step, OutputBundle) and n.step.bundle_name == task.bundle_name
    ]
    sketch.preset_manager.load_preset(task.preset_name, sketch.dag)
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
```

## Revised `build_bundle` signature

```python
def build_bundle(
    sketch_classes: dict[str, type[Sketch]],
    sketches_dir: Path,
    output_dir: Path,
    bundle_name: str,
    workers: int | None = None,
) -> None:
```

`workers=None` uses `ThreadPoolExecutor`'s default (min(32, cpu_count + 4)).
`workers=1` gives sequential behaviour identical to today — useful for debugging
and for asserting correctness in tests.

## Revised `build_bundle` body (sketch)

```python
output_dir.mkdir(parents=True, exist_ok=True)

# Phase 1: discovery
tasks: list[_VariantTask] = []
sketch_meta: dict[str, dict[str, Any]] = {}  # sketch_id -> {slug, name, description, date}

for sketch_id, sketch_cls in sketch_classes.items():
    discovery = _discover_sketch(sketch_id, sketch_cls, sketches_dir, output_dir, bundle_name)
    if discovery is None:
        continue
    sketch_meta[sketch_id] = discovery.meta
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

# Phase 3: manifest
entries: list[dict[str, Any]] = []
for sketch_id, meta in sketch_meta.items():
    variants = produced[sketch_id]
    if not variants:
        log.warning(f"Skipping '{sketch_id}': all presets failed")
        shutil.rmtree(output_dir / meta["slug"], ignore_errors=True)
        continue
    # Restore original preset order (produced list is completion-order)
    ordered = [p for p in _preset_order[sketch_id] if p in set(variants)]
    entries.append({**meta, "variants": [
        {"name": p, "image_path": f"{meta['slug']}/{p}.png"} for p in ordered
    ]})

entries.sort(key=lambda e: e["date"], reverse=True)
bundle_path = output_dir / "manifest.json"
bundle_path.write_text(json.dumps(entries, indent=2))
log.info(f"Wrote {len(entries)} sketch(es) to {bundle_path}")
```

## Helper: `_discover_sketch`

Replaces `_build_sketch`. Does everything up to but not including DAG execution:
validates bundle nodes exist, resolves preset list, creates output dir, returns
`_DiscoveryResult(meta, tasks)` or `None` if the sketch should be skipped.

The discovery instance is discarded after this function returns. It is not shared
with any variant task.

## CLI change

Add `--workers N` to the `build` subcommand:

```python
parser.add_argument(
    "--workers",
    type=int,
    default=None,
    metavar="N",
    help="Number of parallel worker threads (default: auto)",
)
```

Pass `args.workers` through to `build_bundle`.

## Thread safety

| Concern | Safe? | Reason |
|---------|-------|--------|
| Per-variant `Sketch` instances | Yes | Fresh instance per task, no sharing |
| Output file writes | Yes | Each variant writes to a unique path (`<slug>/<preset>.png`) |
| `output_dir.mkdir` | Yes | Called once in main thread before pool starts |
| `sketch_output_dir.mkdir` | Yes | Called once per sketch in discovery (main thread) |
| `logging` | Yes | Python's logging module is thread-safe |
| `produced` dict mutation | Yes | Only appended to from `as_completed` loop in main thread |

## Definition of done (GOOS)

- [ ] Acceptance test: two sketches with two presets each, `workers=2`, asserts all
      four images and the manifest are produced correctly.
- [ ] Unit test: `build_bundle(..., workers=2)` with two sketches produces the same
      manifest and image files as `workers=1`.
- [ ] Unit test: a failing preset for one variant does not prevent other variants
      from completing.
- [ ] Unit test: `build_bundle(..., workers=1)` is behaviourally identical to the
      current sequential implementation (regression guard).
- [ ] `--workers N` CLI flag wired through to `build_bundle`.
- [ ] `mise run lint` passes.
