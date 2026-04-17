# Synthesis — Cross-Flow Audit of Sketchbook

This document aggregates findings across the six entrypoint explorations in
`docs/audits/`: `build-pipeline.md`, `dev-server-startup.md`, `page-routes.md`,
`param-update.md`, `preset-api.md`, and `websocket-watcher.md`.

---

## 1. Cross-cutting concerns

Components that appear in more than one flow, with verdicts aggregated across
all flows that mention them.

| Class / Function | Appears in | Aggregated verdict | Notes |
|---|---|---|---|
| `SketchFnRegistry` | dev-server, page-routes, param-update, preset-api, websocket | **overloaded** (unanimous) | Owns 4–5 concerns: DAG cache, lazy wiring/execution, preset dirty/based_on state, watcher lifecycle, WebSocket connections. Called the "God object of the server layer". |
| `SketchFnRegistry.get_dag` | dev-server, page-routes, param-update, preset-api, websocket | **clean** (unanimous) | Double-checked locking pattern is correct and intentional but undocumented. |
| `SketchFnRegistry._load_dag_lazy` | dev-server, page-routes, preset-api, websocket | **conflict** | dev-server and page-routes call it overloaded (wire + preset + execute + watch registration); preset-api and websocket call it clean (single logical startup sequence). Consensus: sequence is coherent but long enough to benefit from named collaborators. |
| `SketchFnRegistry.set_param` | dev-server, param-update, preset-api, websocket | **conflict** | dev-server and websocket call it clean (tight linear sequence); param-update and preset-api flag it as overloaded (state + persist + execute, disk write before execution success). Consensus: ordering is fragile more than structure is wrong. |
| `SketchFnRegistry.broadcast` / `broadcast_results` | dev-server, param-update, preset-api, websocket | **conflict** | dev-server calls it misplaced (WebSocket fan-out is not a DAG-lifecycle concern); all others call it clean. Consensus: the code inside is fine, but the responsibility belongs in a `ConnectionManager`. |
| `SketchFnRegistry._register_watch` | dev-server, websocket | **unclear / overloaded** | Default-arg closure capture is correct but non-obvious; also defines an inline `on_change` coordinator that could be its own named function or object. |
| `BuiltDAG` | build-pipeline, dev-server, page-routes, param-update, preset-api, websocket | **clean** (unanimous) | Pure data container with two algorithms. |
| `BuiltDAG.topo_sort` | build-pipeline, page-routes, param-update, websocket | **unclear** (majority) | Name implies an active sort but method returns `list(self.nodes.values())`. The topological invariant is enforced in `wire_sketch` and invisible at the call site. build-pipeline notes the implicit assumption; page-routes and param-update call the name misleading; websocket calls it clean since the snapshot behaviour is what callers need. |
| `BuiltDAG.descendants` | dev-server, preset-api, websocket | **unclear** (unanimous) | BFS using `list.pop(0)` is O(N²). Correctness is fine; scaling is not. dev-server additionally flags the whole-graph rescan per queue entry. |
| `BuiltNode` | build-pipeline, dev-server, page-routes, param-update, preset-api, websocket | **clean** (unanimous) | Plain dataclass; mutable `output` and `param_values` are intentional executor contract. Thread-safety concern lives in callers, not in the class. |
| `execute_built` / `execute_partial_built` | all six flows | **clean** (unanimous) | Thin entry points over `_execute_nodes`. |
| `_execute_nodes` | all six flows | **clean** (majority) | param-update calls it slightly overloaded (compute + in-memory mutation + optional disk I/O) but every other flow accepts the loop as is. |
| `_find_ctx_param` | build-pipeline, dev-server, page-routes | **conflict** | build-pipeline and dev-server call it clean; page-routes calls it misplaced (should live in `core/introspect.py` with the other introspection helpers). Both are compatible — function is correct, location is wrong. |
| `wire_sketch` | all six flows | **clean** (unanimous) | Three-phase linear resolution with specific error messages. |
| `@sketch` / `@step` decorators | build-pipeline, dev-server | **clean** | Stamping vs. dual-mode recording is intentional and documented. |
| `BuildingDAG` / `building_sketch()` | build-pipeline, dev-server | **clean** | Pure recorder inside a ContextVar-isolated context manager. |
| `extract_inputs` / `extract_params` | build-pipeline, dev-server, page-routes | **clean** | Well-scoped introspection helpers. |
| `coerce_param` | build-pipeline, param-update | **unclear** | Primitive coercion is fine; rich / non-primitive param types hit a silent `spec.type(raw)` branch that may misbehave on Tweakpane wire forms. |
| `load_preset_into_built` / `load_active_into_built` / `save_active_from_built` / `save_preset_from_built` | build-pipeline, dev-server, param-update, preset-api | **clean** | Each does exactly one disk operation with no side effects beyond the documented mutation. |
| `SketchValueProtocol` / `output_kind` | build-pipeline, page-routes, param-update | **clean** | `@runtime_checkable` protocol + single-dispatch kind check; correctly decouples executor from any concrete image type. |
| `built_node_to_tweakpane` / `param_spec_to_tweakpane` | page-routes, param-update | **clean** | Pure transforms from DAG state to wire schema. `to_tweakpane()` escape hatch is a good pattern. |
| Route handlers in `routes/sketches.py` (`save_preset`, `new_preset`, `load_preset`) | dev-server, page-routes, preset-api | **overloaded** (unanimous) | All three directly mutate `fn_registry._dirty` / `_based_on`; `new_preset` additionally inlines a DAG reset loop. Encapsulation of registry state is broken by route handlers. |
| `sketch_view` route handler | page-routes | **overloaded** | Inlines DAG depth computation (a graph algorithm) alongside template rendering. |
| `sketch_ws_endpoint` | websocket | **overloaded** | Accept + initial dump + tracking + park-until-disconnect in one flat function. |
| `SketchContext` | build-pipeline | **unclear** | Duplicates the mode channel that `execute_built(mode=...)` already carries. Whether it is the canonical mode carrier or a convenience injection point is unclear from the current design. |
| `_build_variant_fn` / `_discover_sketch_fn` | build-pipeline | **overloaded** | Each does five things: wire, filter, preset resolve, meta extraction, task construction (discovery) or wire, load-preset, execute, validate, write-bytes (worker). Most concentrated complexity in the build path. |

---

## 2. Recurring design issues

Patterns that surfaced in more than one flow. Follow-up prompts addressing the
same root cause have been consolidated into single prompts for the backlog
below.

### A. `SketchFnRegistry` is a God object
All five server-touching flows flag it. The decomposition proposals converge
on three collaborators: a `DagCache` (DAG + preset dirty state + lazy load),
a `WatcherCoordinator` (watcher lifecycle and per-path registration), and a
`ConnectionManager` (WebSocket connections and broadcast). Route handlers
reaching into `_dirty` / `_based_on` is a symptom of the same problem.

### B. Disk writes happen before execution succeeds
`set_param`, `new_preset`, and `load_preset` all persist `_active.json`
**before** calling `execute_built`. If execution fails, the persisted state
reflects params that never rendered. `save_preset` has the inverse ordering
concern (named preset written before `_active.json`). The build-pipeline
worker has a weaker variant: it writes the final output file only after
successful execution, but Phase 3 cleanup can leave images from partially
failed sketches on disk briefly.

### C. Shared mutable state without locks across threads
`BuiltNode.output` and `node.param_values` are written by the executor and
can be mutated concurrently from: (1) the asyncio event loop (HTTP param
updates, preset loads), (2) the watchdog OS thread (file-change callbacks),
and (3) potentially multiple concurrent HTTP clients. `SketchFnRegistry._locks`
guards only `_load_dag_lazy`. Related: the `connections` set is implicitly
safe only because all coroutines run on one event loop — an invariant that
is nowhere documented.

### D. `topo_sort` is not a sort
Three flows note the name is misleading — it returns insertion-order values
and relies on a wiring invariant. Either rename to `ordered_nodes()` /
`nodes_in_order()` or document and assert the invariant at construction time.

### E. `BuiltDAG.descendants` is O(N²)
Three flows note that `list.pop(0)` (O(N) per dequeue) and/or the full-node
rescan per queue entry make partial re-execution degrade on wider DAGs.
`collections.deque` + a reverse-adjacency index would make it O(N + E).

### F. `_register_watch` closure pattern is correct but fragile
Default-arg binding avoids the classic late-binding bug, but the technique
is non-obvious, undocumented, and not covered by any test. There is also a
`# type: ignore` on `self._loop` signalling fragility. Both dev-server and
websocket flows independently flag this.

### G. Silent exception handling
Two distinct places swallow errors:
- build-pipeline's `as_completed()` loop catches any worker exception and
  logs a warning, then the build exits cleanly regardless.
- `run_coroutine_threadsafe(broadcast_results(...))` discards the returned
  Future; any exception in broadcast is dropped on the floor. `self._loop`
  can also transiently be `None` between `stop_watcher` and in-flight file
  events.

### H. Dead paths and duplicated code
- `SketchFnRegistry.start_watcher` iterates `self._dags`, which is always
  empty at startup.
- `step.html` has a `data.params ?? data` fallback where `data.params` is
  never set by the API.
- `base.html` runs Tweakpane and preset-bar JS on the index page even though
  the toolbar is hidden there.
- `routes/sketches.py::_list_preset_names` is byte-for-byte identical to
  `core/presets.list_preset_names`.

### I. Two mode channels (`SketchContext.mode` vs executor `mode=` argument)
Both carry the same dev/build information. No enforcement that they agree.
No confirmed userland consumer of `ctx.mode` in any current sketch.

### J. Route handlers own logic that belongs elsewhere
- `sketch_view` computes DAG depth inline.
- `new_preset` inlines a "reset to defaults" loop over the DAG.
- All three mutating preset routes write to `_dirty` / `_based_on`
  directly.
- `_find_ctx_param` lives in `executor.py` but is pure introspection.

---

## 3. Prioritized backlog

All distinct follow-up prompts, de-duplicated and ordered by severity. Prompts
are ready to paste into a new session.

### Correctness bugs

**1. [CRITICAL] Thread race on `BuiltNode` mutations**

Param updates, preset loads, and file-change re-execution all mutate
`BuiltNode.output` and `node.param_values`. Param updates and preset loads
run on the asyncio event loop; file-change callbacks run on the watchdog OS
thread. `_locks` guards only initial wiring, not execution. Concurrent
mutations can corrupt in-memory output and produce inconsistent `_active.json`
/ workdir state.

> In `framework/src/sketchbook/server/fn_registry.py`, `execute_partial_built`
> can be called concurrently from two different threads: the watchdog observer
> thread (via the `on_change` closure in `_register_watch`) and the asyncio
> event loop thread (via `set_param` from `update_param`, and via the three
> mutating preset routes). Both paths mutate `BuiltNode.output` and read
> `node.param_values` without synchronisation. `SketchFnRegistry._locks`
> only guards `_load_dag_lazy`. Audit this race: (1) enumerate every call site
> of any `execute_*` function and the thread it runs on; (2) determine which
> pairs can overlap in time; (3) propose and implement a fix — candidates are
> a per-sketch execution lock, routing all execution onto the asyncio thread
> via `run_in_executor`, or running all execution on the watchdog thread and
> posting only the result to the event loop. Include a regression test that
> interleaves a param update with a file-change callback.

**2. [HIGH] `run_coroutine_threadsafe` drops exceptions and can race with shutdown**

The `on_change` closure in `_register_watch` schedules `broadcast_results`
on the event loop and discards the returned `Future`. Any exception in
broadcast is silently swallowed. `self._loop` is cleared in `stop_watcher`;
a file event still in flight on the watchdog thread can pass `None` to
`run_coroutine_threadsafe`.

> In `SketchFnRegistry._register_watch` in `framework/src/sketchbook/server/fn_registry.py`,
> the `on_change` closure calls `asyncio.run_coroutine_threadsafe(self.broadcast_results(...), self._loop)`
> and never inspects the returned `Future`. Exceptions in `broadcast_results`
> are dropped on the floor. Additionally, `self._loop` can become `None` after
> `stop_watcher()` while a file event is still in flight. Fix both: (1) attach
> a `done_callback` that logs any exception from the future, and (2) guard
> against `self._loop is None` before scheduling. Add a test that asserts
> exceptions raised inside `broadcast_results` are logged, and a test that
> asserts a file event arriving during shutdown does not raise.

**3. [HIGH] `_active.json` persists even when execution fails**

`set_param`, `new_preset`, and `load_preset` all write `_active.json`
**before** `execute_built` runs. `save_preset` writes the named preset
before `_active.json`. Crash or execution failure between steps leaves
state that does not match the workdir.

> Audit disk-write ordering in `SketchFnRegistry.set_param` (fn_registry.py),
> and the `save_preset`, `new_preset`, and `load_preset` routes
> (server/routes/sketches.py). In the first three, `_active.json` is written
> before `execute_built`; if execution fails, the persisted state reflects
> params that never rendered. In `save_preset`, the named preset is written
> before `_active.json` is updated, leaving a window where the dirty flag
> and `based_on` in `_active.json` are stale. Propose and implement an
> ordering that is crash-safe (likely: only persist `_active.json` after
> successful execution). For `save_preset`, consider whether both writes
> should happen atomically via a temp file + rename. Add tests that simulate
> mid-sequence failures (e.g., monkeypatch `execute_built` to raise) and
> assert the persistent state is not corrupted.

**4. [MEDIUM] Build silently swallows per-variant failures and always exits zero**

`build_bundle_fns`'s `as_completed()` loop catches any exception from a
worker, logs a warning, and continues. The CLI always exits zero. Phase 3
cleans up the slug directory when all presets fail, but partial failures
leave an inconsistent manifest with no signal to CI.

> In `framework/src/sketchbook/bundle/builder.py`, the `as_completed()` loop
> in `build_bundle_fns` (approximately lines 228–235) catches every worker
> exception and logs a warning. `cli.build()` then always returns a zero
> exit code. Investigate: (1) enumerate the exception classes that can reach
> this loop — `wire_sketch` ValueErrors, `load_preset_into_built`
> FileNotFoundError, and arbitrary user step errors; (2) decide whether the
> build should track whether any variant failed and return a non-zero exit
> code (or add a `--fail-fast` / `--strict` flag); (3) clarify whether images
> from succeeded variants within a partially-failed sketch should be kept or
> discarded. Add a test that constructs a build where one variant raises and
> asserts the chosen exit-code / cleanup semantics.

**5. [LOW] `coerce_param` silent fall-through for rich types**

Non-primitive `Param`-annotated types hit a `spec.type(raw)` branch that
may raise or silently produce wrong values if the constructor does not
accept the Tweakpane wire form.

> `coerce_param` in `framework/src/sketchbook/core/introspect.py` handles
> `bool`, `int`, `float`, `str` explicitly. For other types it calls
> `spec.type(raw)` — which may raise or return the wrong value when a rich
> type's constructor does not match Tweakpane's wire form. Survey every
> `Param()`-annotated parameter across `sketches/` to find non-primitive
> types. For each, trace what Tweakpane sends and what `coerce_param` would
> produce. Decide between an explicit `TweakpaneCoercible` protocol (with
> `from_tweakpane` / `to_tweakpane` methods) or a round-trip test that
> catches regressions. Implement whichever is chosen.

### Invariant violations and misleading names

**6. `topo_sort` does not sort**

> `BuiltDAG.topo_sort` in `framework/src/sketchbook/core/built_dag.py` returns
> `list(self.nodes.values())` and relies on `wire_sketch` inserting nodes in
> topological order. The invariant is real but invisible at the call site.
> Either rename the method to `nodes_in_order()` / `ordered_nodes()` and
> update every call site, or add a runtime assertion on `BuiltDAG`
> construction that verifies each node's `source_ids` precede it in insertion
> order. Include a test that constructs a DAG out of order and asserts the
> invariant is caught.

**7. `_register_watch` closure pattern is fragile**

> `SketchFnRegistry._register_watch` uses default-argument binding
> (`sid: str = sketch_id`, `d: BuiltDAG = dag`, `nid: str = source_step_id`,
> `wd: Path = workdir`) to avoid the classic Python late-binding closure bug.
> The technique is correct but non-obvious, undocumented, and not covered by
> any test. Additionally, `self._loop` is passed with `# type: ignore`.
> Refactor to replace the default-arg trick with `functools.partial` or an
> explicit factory function with a clear name; resolve the `self._loop`
> type-ignore by restructuring the call site (likely related to follow-up
> #2). Add a unit test that constructs a DAG with two source paths and
> verifies file-change callbacks fire with the correct `source_step_id` for
> each path independently, so the late-binding bug cannot silently return.

### Design clarity

Tasks are grouped by what drives them. Complete Group A before Groups C and D,
since the registry split settles questions that Groups C and D build on.

```
Group B (housekeeping, no deps)
  ↓
Group A (registry decomposition)
  ↓
Group C (build path — mode channel decision informed by A)
  ↓
Group D (documentation pass, everything settled)
```

---

#### Group A — Registry decomposition

`SketchFnRegistry` is the anchor for three follow-on tasks. Do #8 first;
#9, #11, and #15 either become easier or resolve themselves once the split
exists.

**8. Decompose `SketchFnRegistry`**

> `SketchFnRegistry` in `framework/src/sketchbook/server/fn_registry.py` owns
> five distinct concerns: (1) sketch-fn catalog, (2) BuiltDAG cache +
> lazy wiring/execution, (3) preset dirty / based_on state, (4) file watcher
> lifecycle + per-path registration, (5) WebSocket connection set + broadcast
> fan-out. Propose and implement a decomposition — candidate split:
> `DagCache` (2+3), `WatcherCoordinator` (4), `ConnectionManager` (5) —
> with `SketchFnRegistry` becoming a thin facade. Preserve the per-sketch
> locking invariant for lazy load. Update `create_app`, route handlers, and
> tests. Keep the public API of `SketchFnRegistry` stable where possible so
> route handlers need minimal changes.

**9. Route handlers reach into private registry state and own DAG mutations**

> Three preset routes in `framework/src/sketchbook/server/routes/sketches.py`
> (`save_preset`, `new_preset`, `load_preset`) directly write to
> `fn_registry._dirty` and `fn_registry._based_on`. `new_preset`
> additionally iterates `dag.topo_sort()` inline to reset
> `node.param_values[name] = spec.default`. `sketch_view` contains an inline
> DAG-depth computation. Encapsulate these properly: (1) add
> `set_preset_state(sketch_id, dirty, based_on)` on `SketchFnRegistry`
> (or its successor after #8); (2) extract
> `reset_to_defaults(dag: BuiltDAG) -> None` into `core/presets.py`;
> (3) extract the DAG depth computation onto `BuiltDAG` or a server helper.
> Replace all inline logic with calls to the new helpers and add unit tests
> for each. Audit for any remaining direct `_`-prefixed attribute access
> from route handlers.

**11. `_load_dag_lazy` and `set_param` have long linear sequences**

> `SketchFnRegistry._load_dag_lazy` does wire → load active preset → execute
> → register watch. `SketchFnRegistry.set_param` does coerce → store →
> persist → execute. Both are correct but long. After the decomposition in
> #8 they may already be improved; if not, consider naming each step as a
> helper method so the sequence reads at a higher level of abstraction. This
> is a polish pass, not a structural change.

**15. Extract initial-state dump from `sketch_ws_endpoint`**

> `sketch_ws_endpoint` in `framework/src/sketchbook/server/routes/sketches.py`
> handles accept, initial-state dump (topo sort + file existence check +
> message construction), connection tracking, and park-until-disconnect in
> one flat function. Extract the initial-state dump into a helper
> (`dump_initial_state(websocket, dag, workdir)` or similar), ideally owned
> by the `ConnectionManager` from #8. Add a unit test.

---

#### Group B — Naming, location, and dead code

All pure housekeeping with no behaviour change. Fully independent of Group A;
can be done in any order or batched into a single small PR.

**6. `topo_sort` does not sort**

> `BuiltDAG.topo_sort` in `framework/src/sketchbook/core/built_dag.py` returns
> `list(self.nodes.values())` and relies on `wire_sketch` inserting nodes in
> topological order. The invariant is real but invisible at the call site.
> Either rename the method to `nodes_in_order()` / `ordered_nodes()` and
> update every call site, or add a runtime assertion on `BuiltDAG`
> construction that verifies each node's `source_ids` precede it in insertion
> order. Include a test that constructs a DAG out of order and asserts the
> invariant is caught.

**13. Move `_find_ctx_param` to `core/introspect.py`**

> `_find_ctx_param` in `framework/src/sketchbook/core/executor.py` is a
> type-hint introspection utility identical in nature to `extract_inputs`
> and `extract_params` in `core/introspect.py`. Move it, update the import
> in `executor.py`, extend the introspect unit tests to cover it, and
> verify no circular imports are introduced.

**14. Remove duplicate `_list_preset_names`**

> `framework/src/sketchbook/server/routes/sketches.py` defines a private
> `_list_preset_names` that is byte-for-byte identical to
> `core/presets.list_preset_names`. Remove the private copy, add
> `list_preset_names` to the existing `sketchbook.core.presets` import, and
> update the `list_presets` route to call the imported version.

**22. Remove dead code paths**

> Three small dead / misleading paths to clean up: (1) in
> `SketchFnRegistry.start_watcher`, the `for sketch_id, dag in self._dags.items()`
> loop is always empty at startup — either eagerly populate DAGs there or
> remove the loop and clarify the contract; (2) in
> `framework/src/sketchbook/server/templates/step.html`, the
> `data.params ?? data` fallback is unreachable because the API returns a
> flat dict — remove the fallback and add a comment documenting the expected
> shape; (3) in `base.html`, Tweakpane and preset JS execute on the index
> page where the preset bar is hidden — guard the preset / Tweakpane JS
> behind a `{% block scripts %}` that `index.html` overrides to a no-op, or
> stop extending `base.html` from `index.html`.

---

#### Group C — Build path clarity

Both tasks are isolated to the build path and do not touch the server layer.
Do after Group A so the server-side mode plumbing is settled before deciding
which mode channel is canonical.

**10. `_build_variant_fn` concentrates too much logic**

> In `framework/src/sketchbook/bundle/builder.py`, `_build_variant_fn`
> performs five sequential steps: `wire_sketch`, `load_preset_into_built`,
> `execute_built`, validate the output node, write the output bytes to disk.
> This is the most concentrated responsibility in the build path. Evaluate
> splitting into `prepare_variant(task) -> BuiltDAG` (wire + load preset)
> and `materialise_output(dag, dest) -> VariantResult` (validate + write),
> leaving `_build_variant_fn` as a coordinator. Also consider whether
> `_discover_sketch_fn` should split off metadata extraction and task
> construction. For each extracted function, write a unit test that exercises
> it without the full build harness. Confirm no behaviour change.

**12. Two mode channels (`SketchContext.mode` vs executor `mode=`)**

> `execute_built(dag, workdir, mode=...)` controls whether intermediate files
> are written. `SketchContext(mode=...)` is created independently in
> `_discover_sketch_fn` and `_build_variant_fn` and threaded into node
> functions as `ctx`. Investigate: (1) do any sketches under `sketches/`
> actually branch on `ctx.mode`? If not, the ctx channel is currently inert
> in userland. (2) Should mode be owned exclusively by `SketchContext` (and
> the executor read it from the DAG's context), or should the executor
> argument remain canonical? (3) Is there any code path where the two can
> disagree? Pick one canonical channel, remove or reduce the other, and
> document the choice.

---

#### Group D — Documentation and light clarifications

Low-risk documentation and small code changes. Can be done in any order after
the structural work in Groups A and C is settled.

**7. `_register_watch` closure pattern is fragile**

> `SketchFnRegistry._register_watch` uses default-argument binding
> (`sid: str = sketch_id`, `d: BuiltDAG = dag`, `nid: str = source_step_id`,
> `wd: Path = workdir`) to avoid the classic Python late-binding closure bug.
> The technique is correct but non-obvious, undocumented, and not covered by
> any test. Additionally, `self._loop` is passed with `# type: ignore`.
> Refactor to replace the default-arg trick with `functools.partial` or an
> explicit factory function with a clear name; resolve the `self._loop`
> type-ignore by restructuring the call site (likely related to correctness
> fix #2). Add a unit test that constructs a DAG with two source paths and
> verifies file-change callbacks fire with the correct `source_step_id` for
> each path independently, so the late-binding bug cannot silently return.

**16. Document `get_dag`'s double-checked locking**

> `SketchFnRegistry.get_dag` uses a double-checked locking pattern that is
> correct under CPython's GIL but undocumented. Add an inline comment
> explaining why the pattern is safe and what the inner re-check prevents.
> Add a unit test that fires two threads simultaneously against the same
> sketch slug and asserts `_load_dag_lazy` is called exactly once. Note
> whether the pattern remains safe under free-threaded CPython (PEP 703).

**17. Partial re-execution sends no-op events for ancestors**

> `SketchFnRegistry.broadcast_results` iterates `dag.topo_sort()` and checks
> each node against `result.executed` and `result.errors`. For a param change
> on step N, ancestors are neither executed nor errored, so no event fires
> for them. This is correct but worth confirming end-to-end: a browser
> reconnecting mid-flight should not display stale ancestor images. Verify
> in the browser that after a partial re-execution, ancestor images remain
> current and no UI flicker or stale-state appears. Document the invariant
> if confirmed.

**21. Document that `save_preset` does not re-execute or broadcast**

> `save_preset` is the only mutating preset route that does not call
> `execute_built` or `broadcast_results`. This is intentional — saving a
> preset is pure persistence on already-applied values — but nothing in the
> code explains the omission. Add a docstring explaining the intent so a
> future developer does not add a broadcast and silently double-execute.

### Nice-to-haves and edge cases

**18. Type the manifest schema**

> `manifest.json` written in Phase 3 of `build_bundle_fns` is assembled from
> `dict[str, Any]` and serialised with `json.dumps`. Define `ManifestEntry`
> and `VariantEntry` as `TypedDict` (or dataclasses) in
> `framework/src/sketchbook/bundle/builder.py`. Verify the current structure
> matches what the static-site template and any JS consumer expect. Decide
> whether `date` should be validated as ISO-8601 (the manifest sorts by
> string comparison — an out-of-format date would silently produce wrong
> order). Decide whether `image_path` (`f"{slug}/{preset_name}.{ext}"`)
> should be URL-escaped.

**19. Fix O(N²) in `BuiltDAG.descendants`**

> `BuiltDAG.descendants` in `framework/src/sketchbook/core/built_dag.py`
> uses `list.pop(0)` (O(N) per dequeue) and some implementations rescan all
> nodes per queue entry, making BFS O(N²) worst case. Replace with a
> `collections.deque` + `.popleft()`, and precompute a reverse-adjacency
> index (`dependents: dict[str, list[str]]`) when the DAG is finalized in
> `wire_sketch`. Rewrite `descendants` as standard O(N + E) BFS over the
> index. Add a test with a branching DAG asserting correct descendant sets.

**20. `save_preset` triggers full execution on cold DAG**

> `save_preset` calls `fn_registry.get_dag(sketch_id)` purely to snapshot
> `param_values`. If the DAG is not cached, this triggers lazy wiring and
> full execution. Investigate whether `save_preset` should be gated on a
> warm DAG (return 409/412 if cold) or whether reading `_active.json`
> directly is a better snapshot source for this endpoint.

**23. Scope WebSocket replay to the requested step**

> When the browser connects to `/ws/{sketch_id}` from `step.html`, the server
> replays `step_updated` for every node. The client filters to
> `msg.step_id === STEP_ID`. For large pipelines this wastes bandwidth.
> Accept an optional `step_id` query parameter on the WebSocket endpoint
> and replay only the requested node's state. Weigh the added complexity
> against actual pipeline sizes before merging.

**24. Document `connections` threading invariant**

> `SketchFnRegistry.connections` is a `dict[str, set[WebSocket]]` accessed
> from both `broadcast*` (via `run_coroutine_threadsafe`) and
> `sketch_ws_endpoint`. Safety relies on all coroutines executing
> exclusively on the event loop thread. `broadcast` already snapshots the
> set before iterating — good practice. Document this invariant with a
> comment on the `connections` attribute. If any future code path breaks
> it (e.g., thread-pool use), fix with `asyncio.Queue` or
> `loop.call_soon_threadsafe`.

**25. Verify build-worker thread safety empirically**

> `_build_variant_fn` creates a fresh `BuiltDAG` per variant via
> `wire_sketch`, so worker threads should have no shared mutable `BuiltNode`.
> Verify the claim: (1) confirm `wire_sketch` always creates new `BuiltNode`
> instances, not copies of a shared prototype; (2) confirm `sketch_fn`
> itself holds no mutable module-level state; (3) document what locking
> would be required if a future optimisation reused a single wired DAG
> across presets. Add a test that runs the same sketch through many workers
> concurrently and asserts output equivalence to the serial path.

---

## 4. Healthy patterns worth preserving

- **Pure recorder DAGs.** `BuildingDAG` has no execution logic and no knowledge
  of the executor; `BuiltDAG` is a plain resolved container. The recorder /
  resolver / executor split is crisp.
  See `framework/src/sketchbook/core/building_dag.py` and
  `framework/src/sketchbook/core/built_dag.py`.

- **ContextVar-isolated building context.** `building_sketch()` uses a
  `ContextVar` so nested or concurrent `wire_sketch` invocations do not
  collide.
  See `framework/src/sketchbook/core/building_dag.py`.

- **Double-checked locking in `get_dag`.** Fast path avoids the lock; inner
  re-check prevents double-wiring under race. Correct for CPython's GIL.
  See `SketchFnRegistry.get_dag` in `framework/src/sketchbook/server/fn_registry.py`.

- **Typed params with `Annotated[T, Param(...)]`.** `extract_params` requires
  explicit defaults and the `Annotated` pattern — missing metadata is a
  loud error, not a silent fallback.
  See `framework/src/sketchbook/core/introspect.py`.

- **Runtime-checkable structural protocol for outputs.** `SketchValueProtocol`
  decouples the executor from any specific image library; `output_kind`
  single-dispatches on protocol membership.
  See `framework/src/sketchbook/core/protocol.py`.

- **Thin wire-boundary Pydantic model.** `ParamUpdate` lives exactly at the
  HTTP boundary; the core pipeline has no Pydantic dependency.
  See `ParamUpdate` in `framework/src/sketchbook/server/routes/sketches.py`.

- **Three-phase build pipeline.** `build_bundle_fns` separates sequential
  discovery, parallel execution, and sequential manifest assembly into
  explicit, timed, logged phases. Thread pool management is localised
  nowhere else.
  See `framework/src/sketchbook/bundle/builder.py`.

- **Dead-socket pruning in `broadcast`.** `broadcast` snapshots the set,
  collects failed sockets into a `dead` set, and removes them after the
  send loop. No set-mutation-during-iteration risk.
  See `SketchFnRegistry.broadcast` in `framework/src/sketchbook/server/fn_registry.py`.

- **`to_tweakpane()` duck-type escape hatch.** `param_spec_to_tweakpane` calls
  a `to_tweakpane()` method on rich param values if present, letting custom
  types control their own wire representation without the framework knowing
  about them.
  See `framework/src/sketchbook/server/tweakpane.py`.

- **`@sketch` / `@step` separation.** `@sketch` stamps metadata only; `@step`
  is dual-mode (eager vs record-via-ContextVar). Neither decorator couples
  to the executor. The wiring happens in a separate `wire_sketch` pass.
  See `framework/src/sketchbook/core/decorators.py` and
  `framework/src/sketchbook/core/wiring.py`.

- **Loud failures at wire time.** `wire_sketch` validates proxy references
  and missing inputs with specific, actionable error messages rather than
  silent fallbacks.
  See `framework/src/sketchbook/core/wiring.py`.
