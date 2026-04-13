# Simplified Framework — Technical Context

Design session: 2026-04-13. Use this document to resume implementation research.

---

## Decision Record

### Step functions
- Steps are plain Python functions decorated with `@step`
- No `PipelineStep` base class
- No `setup()` / `process()` split — one function, real signature

### Parameter annotation
- Parameters use `Annotated[T, Param(...)]` from `typing`
- `Param` carries: `min`, `max`, `step`, `debounce`, `options`, `label`
- Default values are plain Python defaults in the function signature
- Precedent: FastAPI `Query(...)`, Pydantic v2 `Field(...)`, Typer `Option(...)`

### Input vs parameter distinction
- **Signal**: presence of `Annotated[..., Param(...)]` in annotation = parameter
- **Optional inputs**: `arg: T | None = None` with no `Param` = optional input
- `*` separator used as visual grouping convention (readable but not load-bearing)
- No `Input()` marker needed

### Sketch declaration
- `@sketch(date="...")` decorator + function docstring
- Function name = sketch ID (matches directory name by convention)
- Docstring = description
- `date` = decorator kwarg (site-only, not used by framework)
- Precedent: Click, Typer, FastAPI, argparse

### Sketch context / mode
- `SketchContext` injected by framework when present in function signature
- Carries `mode: Literal["dev", "build"]` (and future fields)
- Detection: framework inspects type annotations, injects matching arg
- Preferred over bare `mode: str` to avoid future parameter explosion

### Deferred execution / DAG
- `@step` functions return proxy objects when called from a sketch context
- Proxy carries: type info, source node reference
- Step implementations receive unwrapped real values
- DAG built implicitly during sketch function execution
- Proxy is thin and invisible at the wiring level

### Step IDs
- Auto-generated from function name
- Collision resolution: append `_1`, `_2` in call order
- Readable preset keys: `circle_grid_mask`, `difference_blend`

### Source files
- `source(path, loader)` — framework protocol function
- `path`: watched by file watcher; change triggers partial re-execution
- `loader`: userland callable `(Path) -> Any`
- Returns a proxy like any step output

### Output declaration
- `output(node, name, presets=[])` — framework protocol function
- Marks terminal node for build output
- Quality (preview vs full) handled by the value type, not the sketch
- No `Postprocess` step needed

### Value type protocol (duck typing)
Framework calls these on any value a step returns:

| Attribute / Method | Required | Purpose |
|---|---|---|
| `extension: str` | Yes | File extension for workdir (`"png"`, `"jpg"`) |
| `to_preview_bytes() -> bytes` | Yes | Fast, low-quality bytes for dev server |
| `to_output_bytes() -> bytes` | Yes | Slow, high-quality bytes for build output |
| `to_html(url: str) -> str` | No | Custom browser renderer; defaults to `<img>` |

MIME type derived from extension; no explicit protocol field needed.

### Value types in userland
- `Image` moves from `framework/src/sketchbook/core/types.py` to `sketches/types.py`
- Framework has zero opinion on image libraries
- OpenCV dependency removed from framework
- `PipelineValue` base class replaced by structural subtyping (`Protocol`)

---

## Open Questions

These need research or spiking before implementation starts.

**1. Proxy mechanism — highest risk**
How does `@step` know it's being called from a sketch context vs. directly? Options:
- `ContextVar[DAG | None]` set by the framework before calling the sketch function
- Thread-local current sketch
- Explicit context manager `with building_sketch(dag):`

Need to spike to confirm the right pattern before designing `@step`.

**2. Parameter introspection**
`inspect.signature()` + `typing.get_type_hints(include_extras=True)` is the path to reading
`Annotated` metadata at runtime. Confirm this works correctly for all param types including
`int | None`, `Annotated[int, Param(...)]`, and combinations.

**3. `SketchContext` injection**
Framework inspects the sketch function signature and injects `SketchContext` by type annotation.
Decide: inject by type only, or by name (`ctx`) + type? Edge case: what if someone has a
`ctx: dict` argument?

**4. Proxy generics**
`Proxy[Image]` for IDE type hints. Needs `__class_getitem__`. Verify mypy/pyright understands
this correctly from the step author's perspective — they should see `Image`, not `Proxy[Image]`.
`typing.overload` or `ParamSpec` may be needed on `@step`.

**5. Multiple outputs**
Can a sketch return multiple outputs? `return output(a, "main"), output(b, "debug")`? Or are
outputs registered as side effects on the DAG context, and return value is ignored? Decide
before implementing `output()`.

**6. Sketch discovery**
Currently scans for `Sketch` subclasses. New design needs to scan for `@sketch`-decorated
functions. The decorator should register the function in a module-level registry, or the
discovery scan should detect the decoration. Verify this works with uvicorn's reload model.

**7. Migration**
Existing sketches (`cardboard`, `kick-polygons`, any others) need rewriting. Is this a flag day
or can old and new coexist? Flag day is simpler; coexistence requires two dispatch paths in the
executor and server.

**8. Value type Protocol class**
Should the framework ship a `Protocol` class documenting the value type interface for IDE
support, even though duck-typed at runtime? Precedent: `os.PathLike`. Probably yes — put it in
`framework/src/sketchbook/core/protocol.py` or similar.

---

## Relevant Current Files

| File | Fate | Notes |
|---|---|---|
| `framework/src/sketchbook/core/step.py` | Replace | `PipelineStep` → `@step` decorator |
| `framework/src/sketchbook/core/sketch.py` | Replace | `Sketch` class → `@sketch` decorator |
| `framework/src/sketchbook/core/params.py` | Refactor | `ParamDef`/`ParamRegistry` stay; `add_param()` DSL goes |
| `framework/src/sketchbook/core/dag.py` | Keep, refactor | DAG logic stays; node creation changes |
| `framework/src/sketchbook/core/executor.py` | Keep | Execution logic largely unchanged |
| `framework/src/sketchbook/core/types.py` | Delete | `Image`, `PipelineValue` move to userland |
| `framework/src/sketchbook/core/presets.py` | Keep | Preset logic unchanged |
| `framework/src/sketchbook/core/watcher.py` | Keep | File watching unchanged |
| `framework/src/sketchbook/steps/source.py` | Replace | `SourceFile` → `source()` function |
| `framework/src/sketchbook/steps/output_bundle.py` | Replace | `OutputBundle` → `output()` function |
| `framework/src/sketchbook/discovery.py` | Refactor | Scan for `@sketch` functions, not `Sketch` subclasses |
| `framework/src/sketchbook/server/tweakpane.py` | Refactor | Read `Annotated`/`Param` instead of `ParamDef` |
| `framework/src/sketchbook/server/routes/params.py` | Refactor | Param reading changes |
| `sketches/cardboard/__init__.py` | Rewrite | |
| `sketches/kick-polygons/__init__.py` | Rewrite | |

---

## Ecosystem Prior Art

| Concept | Prior Art |
|---|---|
| `Annotated[T, Param(...)]` for metadata | FastAPI `Query()`/`Body()`, Pydantic v2 `Field()`, Typer `Option()` |
| Function name → ID, docstring → description | Click, Typer, FastAPI, argparse |
| Deferred execution / proxy DAG | TensorFlow 1.x symbolic tensors, Dask lazy arrays, SQLAlchemy query builder |
| Duck-typed value protocol | Python `Protocol` (PEP 544), `os.PathLike` |
| Default value wrapper | `dataclasses.field()` |
| Injected context by type | FastAPI `Depends()`, pytest fixtures |
| Function signature UI inference | Gradio `gr.Interface` |

---

## Conventions Established

- `@step` functions: positional args = inputs, `*` separator, keyword-only = params (convention)
- `T | None = None` with no `Param`: optional input
- `Param` in `Annotated` is the load-bearing signal for parameters
- `SketchContext`: inject by type; only declare if you need mode or other settings
- `source()` and `output()` are the only framework protocol calls in a sketch body
- Value types live in `sketches/types.py` or sketch-local; never in framework
- Step IDs: function name, `_1` / `_2` suffix for duplicates within a sketch
