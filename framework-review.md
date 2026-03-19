# Framework Code Review

## Layer 1: Core Primitives

### `types.py` — Image
Clean and focused. No issues. Good `classmethod` factory, proper `pathlib` usage.

### `params.py` — ParamDef, ParamRegistry

**SRP concern: `ParamDef.to_dict` leaks UI into domain.** The method is described as "Tweakpane-compatible" — that's a server/presentation concern living inside the core engine. The param definition should be pure domain; serialization to a UI-specific schema belongs in the server layer or an adapter.

**Mutable dataclass.** `override()` uses `setattr` on a frozen-by-convention `@dataclass`. Dataclasses are typically value objects; mutating them in-place defeats that mental model. Consider making `override` return a new `ParamDef` and replacing the entry, or use a plain class instead.

**Latent type-coercion bug.** `set_value` does `param.type(value)`. For `bool`, this is wrong: `bool("false")` is `True`. JSON booleans will work, but any string-based path (query params, form input) will silently produce the wrong value. Consider explicit coercion logic for known types.

### `step.py` — InputSpec, PipelineStep

**`InputSpec` should be a `@dataclass`.** It's a pure data holder with no behavior — three attributes, no methods. Using a plain class is needless ceremony.

**Template method fragility.** `__init__` calls `self.setup()`. `SourceFile` shows the consequence: it must set `self._path` *before* calling `super().__init__()`. This is an ordering footgun — any new subclass that needs state before `setup()` must remember this trick. Consider accepting declared inputs/params as return values from `setup()` or as class-level descriptors instead.

**`add_param`'s `**constraints` catch-all hides the API.** The signature accepts arbitrary kwargs, but only specific fields (`min`, `max`, `step`, `options`) are meaningful. This makes autocompletion and type-checking useless. Spell them out as explicit keyword arguments.

---

## Layer 2: DAG

### `dag.py` — DAGNode, DAG

**`DAGNode.pipe()` violates Liskov Substitution.** The base class declares `pipe()` but only raises `NotImplementedError`. This method has no business on `DAGNode` — it exists solely so `_ManagedNode` (in `sketch.py`) can override it. The base class promises an interface it can't fulfill. Remove it from `DAGNode`; let `_ManagedNode` own it entirely.

**Confusing shadow: `DAGNode._inputs` vs `PipelineStep._inputs`.** Both use `_inputs` as an attribute name but with completely different semantics: one maps input names to source *nodes*, the other maps input names to *specs*. This causes cognitive friction everywhere the two appear together (executor, DAG validator). Rename one — e.g., `DAGNode._sources` or `DAGNode._connections`.

**Linear edge scans.** `_edges` is a flat `list[tuple]`. Every traversal method (`topo_sort`, `descendants`, `connected_components`) iterates the entire edge list to find outgoing edges for a single node. This is O(E) per node, O(N×E) per sort. Build an adjacency dict (`_children: dict[str, list[tuple[str, str]]]`) maintained alongside the edge list. The DAG is small today, but this is an easy fix and it would simplify every traversal method.

**`topo_sort()` rebuilds from scratch every call** and is called from `execute()`, `execute_partial()`, `node_depths()`, `connected_components()`, every route handler that iterates nodes, `save_active`, `save_preset`, etc. Consider caching the sort and invalidating on `add_node`/`connect`.

**`validate()` reaches through two encapsulation layers:** `node.step._inputs` (through DAGNode → PipelineStep → private dict). This is the first symptom of a cross-cutting issue discussed below.

### `executor.py` — execute, execute_partial

**Near-identical duplication.** `execute` and `execute_partial` are ~90% the same code. The only difference is the `if node.id not in subset: continue` guard. Refactor to a single internal `_execute(dag, subset=None)` and have both public functions delegate to it.

**Deep encapsulation violations.** The executor reaches into `node._inputs.values()`, `node.step._param_registry.values()`. If `DAGNode` exposed a `gather_inputs()` method and a `params()` accessor, the executor wouldn't need to know the internal structure of both `DAGNode` and `PipelineStep`.

### `presets.py` — PresetManager

**`dag: Any` everywhere.** Every method that takes `dag` types it as `Any`, defeating static analysis entirely. This should be `dag: DAG`.

**Duplicated param-snapshot logic.** `save_active` and `save_preset` both iterate `dag.topo_sort()` and call `node.step._param_registry.values()` to build the same dict. Extract a `_snapshot_params(dag)` helper.

**Same deep encapsulation reach** as the executor: `node.step._param_registry.load_values()`, `node.step._param_registry.values()`, `node.step._param_registry.reset_to_defaults()`.

### `sketch.py` — Sketch, _ManagedNode

**ID generation is duplicated between `_pipe()` and `add()`.** Both compute `base_name`, look up `_step_counts`, increment, and format `f"{base_name}_{count}"`. Extract a `_next_id(step_class)` method.

**Node creation logic is duplicated between `_pipe()` and `add()`.** Both instantiate the step, apply param overrides, create a workdir path, construct a `_ManagedNode`, and add it to the DAG. Extract a `_make_node(step_class, node_id, param_overrides)` helper.

---

## Layer 3: Server

### `app.py` — The biggest SRP problem

**Seven module-level mutable globals.** `_sketches`, `_candidates`, `_sketch_locks`, `_sketches_dir`, `_watcher`, `_loop`, `_watched_sketches`. The module is simultaneously:

1. An app factory
2. A sketch registry/cache
3. A lazy loader with thread-safe locking
4. A file watcher coordinator
5. A query interface for route handlers (`get_sketch`, `list_sketch_infos`)

This should be an `AppState` (or `SketchRegistry`) class that owns the sketch collection, lazy loading, and watcher registration. The app factory just constructs the state and wires routes. FastAPI's `app.state` or `Depends()` can inject it into handlers cleanly.

The `global` keyword in `create_app` is a strong code smell in Python — it means state management is fully procedural rather than scoped to an object. It also makes test isolation fragile (state bleeds across test runs unless you remember to reset everything).

**`list_sketch_infos` inconsistency.** Uses `getattr(cls, "description", "")` for `description` and `date`, but accesses `cls.name` directly. Either use `getattr` for all or none.

### Routes (`routes/*.py`)

**Deferred imports in every handler body.** Every route does `from sketchbook.server.app import get_sketch` inside the function. This is to work around the module-globals architecture. With proper dependency injection (`Depends(get_sketch_registry)`), these vanish and the circular-import problem is solved structurally.

**`sketch.py` module-level template global.** `_templates` with `init_templates()` setter is the same globals pattern. Use `app.state.templates` or `Depends()`.

**`ws.py` untyped parameters.** `broadcast_results(sketch_id, dag, result)` and `broadcast_preset_state(sketch_id, preset_manager)` accept untyped args. Use `DAG`, `ExecutionResult`, `PresetManager`.

### `ws.py` — Connection management

Module-level `_connections` defaultdict. Same pattern — should live on a state object so it's scoped to the app lifetime and naturally cleaned up between tests.

---

## Layer 4: Site Builder

### `builder.py`

**`build_site` does too much in one function** (~90 lines): discovers SiteOutput nodes, filters presets, executes pipelines, saves images, renders templates, and builds the feed. Break it up: `_build_sketch(sketch_id, sketch_cls, ...)` for the per-sketch loop body, `_snapshot_variants(sketch, presets, site_nodes, variants_dir)` for the preset iteration and baking.

---

## Cross-Cutting Issues

### 1. The `_` prefix lie (most pervasive issue)

`_inputs`, `_param_registry`, `_path` are all `_`-prefixed (private by convention) but accessed from outside their owning class **constantly**: executor, DAG validator, preset manager, server routes, watcher, sketch builder. The underscore is a lie — these are effectively public API surfaces.

**Fix:** Either drop the `_` prefix and acknowledge they're public, or (better) add proper accessor methods to `PipelineStep` and `DAGNode`:
- `PipelineStep.input_specs` → `dict[str, InputSpec]`
- `PipelineStep.param_values()` → `dict[str, Any]`
- `PipelineStep.param_schema()` → `dict[str, dict]`
- `PipelineStep.load_params(data)` → delegates to registry
- `DAGNode.source_nodes` → `dict[str, DAGNode]` (replaces `_inputs`)

This would also resolve the naming collision between `DAGNode._inputs` and `PipelineStep._inputs`.

### 2. No clear "param snapshot" abstraction

Three different subsystems (executor, preset manager, server routes) all reach into `node.step._param_registry` to read or write params. The registry is the implementation detail; what they actually need is:
- "Give me this node's current param values" (executor, preset manager)
- "Set a param value on this node" (route handler)
- "Load a batch of param values" (preset manager)
- "Get the UI schema" (route handler)

These should be methods on `DAGNode` or `PipelineStep`, not reached through two levels of indirection.

### 3. Missing protocols/ABCs for the step interface

`PipelineStep.process()` returns `Any` and receives `dict[str, Any]` for both inputs and params. There's no type-safe contract between the framework and step implementations. This is acceptable at this stage, but as the framework matures, consider a `Protocol` or generic type parameter for the output type.

---

## Summary: Priority Ranking

| Priority | Issue | Scope |
|----------|-------|-------|
| **High** | ~~`app.py` module globals → `SketchRegistry` class~~ ✅ | Server |
| **High** | `execute`/`execute_partial` duplication → single function | Core |
| **High** | Encapsulation violations → accessor methods on `PipelineStep`/`DAGNode` | Cross-cutting |
| **Medium** | `DAGNode._inputs` / `PipelineStep._inputs` naming collision | Core |
| **Medium** | `_pipe()`/`add()` duplication in `Sketch` | Core |
| **Medium** | `ParamDef.to_dict` UI concern in core | Core |
| **Medium** | `dag: Any` typing in `PresetManager` | Core |
| **Medium** | `InputSpec` should be a `@dataclass` | Core |
| **Low** | `DAGNode.pipe()` Liskov violation | Core |
| **Low** | ~~Deferred imports in route handlers (symptom of globals)~~ ✅ | Server |
| **Low** | `build_site` function length | Site |
| **Low** | Edge adjacency dict for graph traversals | Core |
| **Low** | `bool` coercion bug in `ParamRegistry.set_value` | Core |
