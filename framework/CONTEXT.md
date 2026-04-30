# Framework Context

The `framework/` sub-project is the Sketchbook engine: a reactive, DAG-based pipeline runner for creative coding. It provides the minimal protocol surface that sketch authors use, plus the infrastructure to execute, watch, serve, and build pipelines.

The framework is a generic, publishable package. It has no knowledge of any specific sketch, no image library dependency, and no opinion on value types.

## Domain vocabulary

**Sketch** — a Python function decorated with `@sketch` that wires a pipeline by calling `@step` functions and returning nothing. It is the entry point for one creative piece.

**Step** — a plain Python function decorated with `@step`. Positional args are pipeline inputs; keyword-only args annotated with `Annotated[T, Param(...)]` are tunable parameters.

**Source** — a watched file input declared with `source(path, loader)`. When the file changes, only the affected subgraph re-executes.

**Output** — a terminal declaration: `output(proxy, bundle_name, presets=[])`. Marks which node produces the build artifact.

**Param** — metadata for a tunable parameter: `Param(min, max, step, label, debounce, options)`. Declared inside `Annotated[T, Param(...)]` on a keyword-only step argument.

**SketchContext** — a runtime object (`mode: Literal["dev", "build"]`) injected by the framework into any step or sketch that declares it as a positional argument by type annotation. Carry it when a step needs to behave differently between dev preview and build output.

**BuildingDAG** — the transient structure accumulated while a sketch function runs. Records `StepCall`, `SourceRecord`, and `OutputRecord` objects. Held in a `ContextVar` so `@step` knows it's in a sketch context.

**Proxy** — a deferred handle returned by `@step` calls during sketch wiring. Carries only `step_id`. Downstream steps receive it as an argument; the framework resolves it to a real value at execution time.

**BuiltDAG** — the fully resolved, topologically ordered graph. Produced by `wire_sketch()`. Contains `BuiltNode` entries (each with `fn`, `source_ids`, `param_schema`, `param_values`, `ctx`), `source_paths` for the watcher, and `output_nodes` for the builder.

**SketchValueProtocol** — the structural duck-typed interface the framework expects from step return values. Three members required: `extension: str`, `kind: str`, `to_bytes(mode: Literal["dev", "build"]) -> bytes`. One optional: `to_html(url: str) -> str` (defaults to `<img>` if absent). Plain Python primitives (`int`, `float`, `str`) are also valid — the framework falls back to `.txt` + `str()`.

**Workdir** — the ephemeral scratch directory for a sketch (`.workdir/` under the sketch directory). The executor writes one file per node after each run. Fully disposable.

## Protocol surface (what sketch authors import)

```python
from sketchbook.core.decorators import sketch, step, Param, SketchContext
from sketchbook.core.building_dag import source, output
```

Everything else in `framework/src/sketchbook/` is internal.

## Key mechanics

### Sketch wiring (BuildingDAG → BuiltDAG)

1. `wire_sketch(fn, ctx)` activates a fresh `BuildingDAG` via `ContextVar`.
2. The sketch function runs; each `@step` call checks `_active_dag.get()` and, if present, calls `dag.record_step()` instead of executing — returning a `Proxy`.
3. `source()` and `output()` also record into the active DAG.
4. After the sketch returns, `wire_sketch` walks the recorded calls in call order (which is already topological, since Python evaluates arguments before calls) and builds a `BuiltDAG`.
5. Input wiring: `extract_inputs(fn)` reads positional parameters; `Proxy` args are matched by position to `InputSpec` entries. Required inputs with no `Proxy` raise `ValueError` at wire time.
6. Param extraction: `extract_params(fn)` reads keyword-only `Annotated[T, Param(...)]` parameters via `typing.get_type_hints(include_extras=True)`.

### Execution

`execute_built(dag, workdir, mode)` walks nodes in `nodes_in_order()` (insertion = topo order). For each node it resolves inputs from upstream `node.output` values, injects `SketchContext` if declared, calls `fn`, and writes to workdir. `execute_partial_built(dag, start_ids, workdir, mode)` re-executes only the affected subgraph (start IDs + descendants).

### Step IDs

Auto-derived from `fn.__name__`. Collisions within a sketch get `_1`, `_2` suffixes in call order. Source nodes use `source_<stem>`. These IDs are the keys in preset JSON files — changing a function name is a breaking preset change.

### SketchContext injection

`find_ctx_param(fn)` scans the function signature for an argument whose type annotation is `SketchContext`. The executor injects it by keyword. Detection is by type only — the parameter name is irrelevant.

## File map

| Path | Role |
|---|---|
| `core/decorators.py` | `@sketch`, `@step`, `Param`, `SketchContext`, `SketchMeta` |
| `core/building_dag.py` | `BuildingDAG`, `Proxy`, `source()`, `output()`, `building_sketch()` context manager |
| `core/built_dag.py` | `BuiltDAG`, `BuiltNode`, `ParamSpec` |
| `core/wiring.py` | `wire_sketch()` — BuildingDAG → BuiltDAG |
| `core/executor.py` | `execute_built()`, `execute_partial_built()`, `ExecutionResult` |
| `core/introspect.py` | `extract_inputs()`, `extract_params()`, `find_ctx_param()`, `coerce_param()` |
| `core/protocol.py` | `SketchValueProtocol`, `output_kind()` |
| `core/presets.py` | Preset load/save |
| `core/watcher.py` | File watching |
| `discovery.py` | Scans for `@sketch`-decorated functions |
| `server/` | FastAPI dev server, WebSocket connection manager, DAG cache, fn registry, Tweakpane UI |
| `bundle/` | Static site builder |
| `cli.py` | Entry point (`sketchbook dev`, `sketchbook build`) |
| `scaffold.py` | `mise run sketches:new` backing implementation |

## Hard boundaries

- `framework/` never imports from `sketches.*`. Value types, image libraries, and domain-specific steps all live in userland.
- `framework/tests/` defines its own concrete step functions inline or in `tests/steps.py` — never imports from sketches.
- The only way for a pipeline to write outside `.workdir/` is through an `output()` node. No step may write to the workspace directly.
