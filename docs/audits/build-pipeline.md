# Build Pipeline — End-to-End Sequence

## Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant CLI as cli.build()
    participant Discovery as discover_sketch_fns()
    participant Builder as build_bundle_fns()
    participant DiscoverFn as _discover_sketch_fn()
    participant Pool as ThreadPoolExecutor
    participant Worker as _build_variant_fn() [worker thread]
    participant WireSketch as wire_sketch()
    participant BuildingDAG as building_sketch() / BuildingDAG
    participant BuiltDAG as BuiltDAG
    participant Presets as load_preset_into_built()
    participant Executor as execute_built()
    participant Manifest as Phase 3 (manifest assembly)

    User->>CLI: uv run build [--bundle NAME] [--output DIR] [--workers N]

    note over CLI: Parse args, resolve paths

    CLI->>Discovery: discover_sketch_fns(sketches_dir)
    note over Discovery: Mutates sys.path, imports package,<br/>pkgutil.iter_modules over submodules,<br/>finds callables with __is_sketch__ == True
    Discovery-->>CLI: dict[slug, Callable]

    CLI->>Builder: build_bundle_fns(sketch_fns, sketches_dir, output_dir, bundle_name, workers)

    rect rgb(240, 248, 255)
        note over Builder: PHASE 1 — Sequential Discovery (main thread)
        loop for each (sketch_key, sketch_fn)
            Builder->>DiscoverFn: _discover_sketch_fn(sketch_key, sketch_fn, ...)
            DiscoverFn->>WireSketch: wire_sketch(sketch_fn, SketchContext(mode="build"), sketch_dir)
            WireSketch->>BuildingDAG: building_sketch() [context manager]
            BuildingDAG-->>WireSketch: fresh BuildingDAG (stored in ContextVar)
            WireSketch->>WireSketch: fn() — sketch function runs, recording source()/step()/output() calls
            WireSketch->>BuiltDAG: resolve sources → BuiltNode (loader lambda)
            WireSketch->>BuiltDAG: resolve step calls → BuiltNode (validate proxy refs, extract params)
            WireSketch->>BuiltDAG: resolve output() calls → output_nodes list
            WireSketch-->>DiscoverFn: BuiltDAG
            DiscoverFn->>DiscoverFn: filter output_nodes by bundle_name
            DiscoverFn->>Presets: list_preset_names(presets_dir)
            Presets-->>DiscoverFn: sorted list of preset names (excludes _active)
            DiscoverFn->>DiscoverFn: apply node_presets filter; build _VariantTaskFn list
            DiscoverFn->>DiscoverFn: read sketch_fn.__sketch_meta__ for name/description/date
            DiscoverFn-->>Builder: _DiscoveryResultFn (meta, tasks, preset_order)
        end
        note over Builder: tasks = flat list of all _VariantTaskFn<br/>sketch_meta and preset_order keyed by sketch_key
    end

    rect rgb(255, 248, 240)
        note over Builder,Worker: PHASE 2 — Parallel Execution (worker threads)
        Builder->>Pool: ThreadPoolExecutor(max_workers=workers)
        loop for each _VariantTaskFn (submitted all at once)
            Builder->>Pool: pool.submit(_build_variant_fn, task)
        end

        note over Pool,Worker: --- THREAD BOUNDARY ---

        loop for each future in as_completed(futures)
            Pool->>Worker: _build_variant_fn(task) [worker thread]
            Worker->>WireSketch: wire_sketch(task.sketch_fn, SketchContext(mode="build"), task.sketch_dir)
            note over Worker: Fresh BuiltDAG per variant (no shared mutable state)
            WireSketch-->>Worker: BuiltDAG
            Worker->>Presets: load_preset_into_built(dag, presets_dir, preset_name)
            note over Presets: Reads <preset_name>.json, coerces param values<br/>into BuiltNode.param_values
            Presets-->>Worker: (mutates dag in place)
            Worker->>Executor: execute_built(dag, Path(tmp), mode="build")
            note over Executor: Iterates topo_sort(), for each node:<br/>• gather upstream outputs<br/>• call node.fn(**inputs, **params, ctx?)<br/>• in build mode: does NOT write intermediate files<br/>• on failure: mark node + propagate to descendants
            Executor-->>Worker: ExecutionResult (ok, errors, executed)
            Worker->>Worker: read output_node.output from BuiltDAG
            Worker->>Worker: dest.write_bytes(val.to_bytes("build"))
            note over Worker: Writes only the final output file<br/>to sketch_output_dir/<preset_name>.<ext>
            Worker-->>Pool: _VariantResultFn (sketch_key, preset_name, ok, extension)

            note over Pool,Builder: --- THREAD BOUNDARY (back to main) ---

            Pool-->>Builder: future.result() or exception
            Builder->>Builder: on exception: log warning, continue<br/>on ok: record produced[sketch_key][preset_name] = ext
        end
    end

    rect rgb(240, 255, 248)
        note over Builder,Manifest: PHASE 3 — Manifest Assembly (main thread, sequential)
        loop for each sketch_key in sketch_meta
            Builder->>Manifest: build entries list
            note over Manifest: If all presets failed for a sketch:<br/>  shutil.rmtree(output_dir/slug) and skip<br/>Otherwise: assemble {slug, name, description, date, variants}
        end
        Manifest->>Manifest: entries.sort(key=date, reverse=True)
        Manifest->>Manifest: write manifest.json (output_dir/manifest.json)
    end

    Builder-->>CLI: (returns None)
    CLI->>User: print "Built bundle '<name>' with N sketch(es) -> <output_dir>"
```

---

## Responsibility Verdicts

| Component | File | Verdict | Rationale |
|---|---|---|---|
| `cli.build()` | `cli.py` | **clean** | Thin entry point: parse args, delegate to `discover_sketch_fns` and `build_bundle_fns`, print summary. No business logic. |
| `discover_sketch_fns()` | `discovery.py` | **clean** | Single job: scan a directory for `__is_sketch__` callables. Correctly separates discovery from wiring. |
| `build_bundle_fns()` | `bundle/builder.py` | **clean** | Orchestrates the three phases clearly; each phase is explicit, timed, and logged. Thread pool management is localised here and nowhere else. |
| `_discover_sketch_fn()` | `bundle/builder.py` | **overloaded** | Does five things: wires the sketch, filters output nodes, resolves presets, reads sketch metadata from `__sketch_meta__`, and constructs the task list. The metadata extraction and task construction could be split out. Not a crisis, but the function is doing more than its name suggests. |
| `_build_variant_fn()` | `bundle/builder.py` | **overloaded** | Wire + load-preset + execute + validate output node + write bytes — five distinct responsibilities in one function. This is the most concentrated complexity in the build path. Deserves its own follow-up (see below). |
| `_VariantTaskFn` | `bundle/builder.py` | **clean** | Pure data; all fields needed by the worker, nothing more. |
| `_VariantResultFn` | `bundle/builder.py` | **clean** | Minimal result bag. `extension` field with a stringly typed default (`"png"`) is worth noting (see follow-ups). |
| `_DiscoveryResultFn` | `bundle/builder.py` | **clean** | Correctly groups the three discovery outputs needed by Phase 3. |
| `SketchContext` | `core/decorators.py` | **unclear** | A `@dataclass` with a single `mode: Literal["dev", "build"]` field. It exists to thread build-mode awareness into step functions, but the executor already receives `mode` directly. The indirection adds a second channel carrying the same information. Whether `SketchContext` should be the canonical mode carrier or just a convenience injection point is not clear from the current design. |
| `@sketch` decorator | `core/decorators.py` | **clean** | Stamps `__is_sketch__` and `__sketch_meta__` — no side effects, purely additive. |
| `@step` decorator | `core/decorators.py` | **clean** | Dual-mode (eager vs deferred via `ContextVar`) is the intentional design; clearly documented. |
| `BuildingDAG` | `core/building_dag.py` | **clean** | Pure recorder. No execution logic, no side effects, no knowledge of the executor. |
| `building_sketch()` | `core/building_dag.py` | **clean** | Context manager that isolates `ContextVar` state. Nested invocations are safe. |
| `wire_sketch()` | `core/wiring.py` | **clean** | One job: run the sketch function inside `building_sketch()`, then resolve the `BuildingDAG` into a `BuiltDAG`. Validation is explicit and error messages are informative. |
| `BuiltDAG` | `core/built_dag.py` | **clean** | Thin container. `topo_sort()` relies on insertion order being topological — this is correct because `wire_sketch` processes sources before steps, and steps are recorded in Python evaluation order, but it is an implicit assumption not enforced by the data structure. |
| `BuiltNode` | `core/built_dag.py` | **clean** | Flat dataclass. `output: Any = None` is mutable shared state that the executor writes — acceptable for a single-threaded dev path, but see thread-safety follow-up for the build path. |
| `execute_built()` | `core/executor.py` | **clean** | Walks topo order, propagates failures to descendants, skips intermediate writes in build mode. The `mode` guard at line 108 is minimal and correct. |
| `execute_partial_built()` | `core/executor.py` | **clean** | Computes descendant set via BFS, delegates to `_execute_nodes`. |
| `_execute_nodes()` | `core/executor.py` | **clean** | Centralised execution loop; failure propagation is explicit and well-logged. |
| `_find_ctx_param()` | `core/executor.py` | **clean** | Small helper, fallible gracefully, logs warnings on type resolution failure. |
| `load_preset_into_built()` | `core/presets.py` | **clean** | Reads one preset JSON, applies values, raises `FileNotFoundError` on missing file (loud error). |
| `list_preset_names()` | `core/presets.py` | **clean** | Pure filesystem query; correctly excludes `_active`. |
| `_apply_values()` | `core/presets.py` | **clean** | Thin adapter that coerces raw JSON values to declared param types. |
| `SketchValueProtocol` | `core/protocol.py` | **clean** | Structural protocol with `@runtime_checkable`; correctly decouples the executor from any specific image type. |
| `extract_inputs()` | `core/introspect.py` | **clean** | Well-scoped: only positional params, skips `SketchContext`, handles optional annotation unwrapping. |
| `extract_params()` | `core/introspect.py` | **clean** | Correctly restricts to keyword-only `Annotated[T, Param(...)]` params; raises loudly on missing defaults. |
| `coerce_param()` | `core/introspect.py` | **clean** | Conservative coercion; unknown types are returned unchanged rather than silently converting. |

---

## Follow-up Prompts

---

### FU-1: Does `_build_variant_fn` do too much?

```
In framework/src/sketchbook/bundle/builder.py, _build_variant_fn() performs
five sequential steps: wire_sketch, load_preset_into_built, execute_built,
validate the output node, and write the output bytes to disk.  This makes it
the most concentrated unit of responsibility in the build path.

Investigate whether splitting it into smaller collaborators would improve
testability and error attribution.  Specifically:

  1. Could "wire + load preset" be a standalone function (e.g. prepare_variant)?
     What would the unit test for that function look like?

  2. Could "validate output node + write bytes" be a standalone function (e.g.
     materialise_output)?  What is the minimal interface it needs?

  3. Does the current structure make it hard to write a unit test for
     _build_variant_fn that does not touch the filesystem?  (It uses
     tempfile.TemporaryDirectory internally, so the answer is probably no —
     but confirm.)

  4. After the proposed split, would _build_variant_fn become a pure
     coordinator with no testable logic of its own?  If so, is that better or
     worse than the current structure?
```

---

### FU-2: Is `SketchContext(mode="build")` the right abstraction for suppressing disk I/O?

```
In core/executor.py, the decision to skip intermediate writes is controlled
by the `mode` argument to execute_built() (line 108), NOT by SketchContext.
However, SketchContext(mode="build") is also created in both _discover_sketch_fn
and _build_variant_fn and threaded into every BuiltNode — giving step functions
a way to observe the build mode via their ctx parameter.

This creates two parallel mode channels:

  Channel A: execute_built(dag, workdir, mode="build") — controls intermediate
             file writes in the executor.
  Channel B: SketchContext(mode="build") injected into nodes — controls
             whatever individual steps choose to do differently in build mode.

Investigate:
  1. Are there any step functions in sketches/ that actually branch on
     ctx.mode?  If not, channel B is currently inert in userland.
  2. Should mode be owned exclusively by SketchContext (and the executor read
     it from the DAG's context), or should it remain a separate executor
     argument?  What is the cost of each approach?
  3. Is it possible for the two channels to disagree (e.g. ctx.mode="dev" but
     executor mode="build")?  Is there a guard against this?
```

---

### FU-3: Error handling when a variant raises mid-flight

```
In build_bundle_fns() (bundle/builder.py lines 228-235), exceptions from
worker threads are caught by the as_completed() loop:

    try:
        result = future.result()
    except Exception as exc:
        log.warning(f"  variant '{task.sketch_key}/{task.preset_name}' raised: {exc}")
        continue

This silently skips the failed variant and continues.  Investigate:

  1. What categories of exception can _build_variant_fn raise that are NOT
     already handled internally (i.e. that reach the as_completed loop)?
     Consider: wire_sketch raising ValueError on bad proxy refs,
     load_preset_into_built raising FileNotFoundError, and arbitrary
     exceptions from user step functions.

  2. Is swallowing a per-variant exception and continuing the right policy?
     What if every variant of a sketch fails — is the output_dir/slug
     directory cleaned up?  (Phase 3 calls shutil.rmtree if preset_ext_map
     is empty, so the directory is removed, but the images written by
     succeeded variants within a partially-failed sketch stay on disk until
     then — is that correct?)

  3. Should the build exit non-zero if any variant failed?  Currently cli.build()
     always exits cleanly.  A --fail-fast flag or a non-zero exit code on
     partial failure would be useful for CI.
```

---

### FU-4: Is the manifest format well-typed or stringly typed?

```
The manifest.json written in Phase 3 of build_bundle_fns() is assembled from
plain dict[str, Any] structures and serialised with json.dumps.  There is no
dataclass or TypedDict modelling the manifest schema.

Investigate:
  1. Define (as TypedDict or dataclass) what ManifestEntry and VariantEntry
     should look like.  Does the current dict structure match what downstream
     consumers (e.g. the static site template or any JS that reads the
     manifest) actually expect?

  2. The "date" field comes from SketchMeta.date which is a plain str with no
     validated format.  Is this intentional?  Should it be ISO-8601?  The
     manifest sorts by date (reverse=True) as a string comparison — would
     an out-of-format date silently produce wrong sort order?

  3. The "image_path" field is constructed as f"{slug}/{preset_name}.{ext}".
     This is a relative path, not a URL.  Is this documented anywhere?  What
     breaks if a preset name contains a path separator or URL-unsafe characters?

  4. Consider adding a ManifestEntry TypedDict and a VariantEntry TypedDict
     in bundle/builder.py to make the schema explicit and catch dict key typos
     at type-check time.
```

---

### FU-5: Thread safety of `BuiltNode.output` in the build worker pool

```
In core/built_dag.py, BuiltNode has a mutable field:

    output: Any = None

The executor writes to this field during execution.  In the build path,
_build_variant_fn creates a fresh BuiltDAG per variant via wire_sketch(), so
each worker gets its own graph with its own BuiltNode instances.  There is no
shared mutable state between workers.

Verify this claim:
  1. Confirm that wire_sketch() always creates new BuiltNode instances (not
     copies of a shared prototype).  Pay attention to whether any object is
     captured by reference in the loader lambdas created by _make_source_fn().
  2. Confirm that the sketch_fn callable itself (shared across all workers
     for a given sketch) contains no mutable module-level state that would
     create a data race.
  3. If a future optimisation were to reuse a single wired DAG across presets
     (to avoid re-wiring N times for N presets of the same sketch), what
     locking strategy would be required?
```
