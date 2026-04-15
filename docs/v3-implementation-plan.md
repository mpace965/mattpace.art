# Sketchbook v3 — Implementation Plan

## Overview

This plan rewrites the framework around a single principle: normal Python is the interface.
`@step` functions replace `PipelineStep` subclasses. `@sketch` functions replace the `Sketch`
class and its `build()` DSL. The DAG still exists — it's built implicitly as the sketch function
runs — but it's invisible to the sketch author.

Design background: `docs/simplified-framework-design.md`,
`docs/simplified-framework-technical-context.md`, spike: `docs/spike_proxy_mechanism.py`.

This plan follows the GOOS double-loop. We grow the new system end-to-end from a walking
skeleton. Each increment is defined by a failing acceptance test that drives implementation
across all layers simultaneously. The old framework code stays alive and untouched until the
final increment ports the real sketches and deletes it.

---

## Writing a detailed increment plan

Before starting any increment, write a standalone implementation plan to
`docs/v3-increment-<N>-plan.md`. The plan is the contract between the high-level increment
description above and the actual coding session. Write it to a file — do not output it inline.

A complete plan contains the following sections, in this order:

**Acceptance criterion** — copy the acceptance test description verbatim from this document.

**Current state** — read the branch and list what already exists that is relevant to this
increment (stubbed types, partial implementations, prior-art files) and what is absent. This
prevents re-deriving context during implementation.

**GOOS double-loop** — the outer loop is the acceptance test; the inner loop is one unit test
per collaborator. The section must make the loop structure explicit:

- Step 0: write the acceptance test and run it — it must fail before any implementation starts.
  Include the exact `uv run pytest` command and state the expected failure mode.
- One numbered inner loop per collaborator (a class, function, or module boundary). Each loop
  has three parts in order:
  1. The failing unit test(s) — written and run before touching implementation.
  2. The implementation — minimum code to make those tests pass.
  3. An explicit "run unit tests — all pass" checkpoint before moving to the next loop.
- An outer loop check at the end: run the acceptance test again and confirm it goes green.

**Files to create / files to modify** — two tables listing every file touched, with a one-line
description of the change. Written before implementation so the scope is visible upfront.

**Acceptance test (full spec)** — the complete pytest source for the acceptance test, ready to
paste into the file. Written in the plan so it can be reviewed before any code changes.

**Prior art** — a table mapping existing files to their role as reference or reuse. Prevents
re-implementing things that already exist in the old path.

**Definition of done** — a checkbox list. Every new class, function, and route gets at least
one checkbox. All boxes must be checked before the increment is considered complete.

**Manual verification** — step-by-step instructions a human can follow after all automated
checks pass, to confirm the browser-side behaviour that tests cannot cover. Includes:
- any sketch edits needed to exercise the feature (use `cardboard_v3` as the v3 demo sketch)
- the `mise run sketches:dev` start command
- specific URLs to open and what to look for
- `curl` commands for any new API endpoints, with expected output
- browser DevTools checks (Network/WS) where relevant
- a "commit the sketch change" note if the sketch was modified — `cardboard_v3` is the
  persistent v3 demo and changes to it are kept, not reverted

---

## Migration strategy

Same repo. Additive cutover. No fork.

The new protocol (`@step`, `@sketch`, `source()`, `output()`) is additive until Increment 5.
New acceptance tests use new test fixtures; old acceptance tests continue passing against the
old code path. The coexistence window is intentional and short — all four sketches are ported
in a batch in Increment 5, then the old code is deleted.

The invariant: the site never goes dark. Existing sketches run on the old path until Increment 5
replaces them.

---

## Decisions log

| Decision | Choice |
|---|---|
| Step authoring | `@step`-decorated functions (was `PipelineStep` subclasses) |
| Sketch declaration | `@sketch(date=...)` + function docstring (was `Sketch` subclass + class attrs) |
| Parameter annotation | `Annotated[T, Param(...)]` keyword-only args (was `add_param()` in `setup()`) |
| Input declaration | Positional-or-keyword args without `Param` in annotation (was `add_input()`) |
| DAG construction | Implicit via `ContextVar` + proxy objects (was explicit `build()` DSL) |
| Sketch context | `SketchContext` injected by type annotation (was `self.mode`) |
| Value type serialization | `to_bytes(mode)` — single method, mode-aware (was `to_bytes()` fixed quality) |
| Value type protocol | Structural (duck-typed `SketchValueProtocol`) — `to_bytes(mode)`, `extension` |
| Image and Color | Userland (`sketches/types.py`), not framework |
| Source node IDs | `source_<path-stem>`, collision suffix `_1`, `_2` |
| Output node IDs | `output_<bundle-name>`, collision suffix `_1`, `_2` |
| Step node IDs | Function name, collision suffix `_1`, `_2` (was `class_snake_case_0`) |
| Proxy generics | Deferred (authors never interact with proxies directly) |
| Multiple outputs | `output()` is a side-effect call; return value ignored |
| Sketch discovery | `__is_sketch__` attribute stamped by `@sketch`; no global singleton registry |
| Userland duplication | Intentional — duplicate steps across sketches until abstraction is clearly stable |

---

## Resolved open questions

**Proxy mechanism** — Settled by the spike. `ContextVar[BuildingDAG | None]` +
`building_sketch()` context manager. Nested contexts are isolated via token reset.

**Parameter introspection** — `inspect.signature()` +
`typing.get_type_hints(include_extras=True)`. `include_extras=True` preserves `Annotated`
wrappers. Same approach as FastAPI. No spike needed.

**SketchContext injection** — Inject by exact type match. Framework inspects sketch and step
signatures, injects `SketchContext` wherever the annotation is exactly `SketchContext`. Name
doesn't matter.

**Source node IDs** — `source_<path.stem>`, e.g. `source("assets/cardboard.jpg", ...)` →
`source_cardboard`. Avoids collision with user step names.

**Color** — Moves to `sketches/types.py` alongside `Image`. Keeps `to_tweakpane()`. Framework
detects custom param types by duck-typing: calls `to_tweakpane()` if present.

**Internal DAG representation** — New types (`BuiltDAG`, `BuiltNode`) separate from the old
`DAG`/`DAGNode`. No hybrid. Old types deleted in Increment 5.

**Postprocess step** — Eliminated entirely. `Image.to_bytes(mode)` returns fast low-quality
bytes in `"dev"` mode and slow high-quality bytes in `"build"` mode.

---

## New internal types (overview)

These are introduced incrementally across the first four increments. Full signatures are not
repeated in every increment; they're defined here as a reference.

```
# core/decorators.py
Param           — dataclass: min, max, step, label, debounce, options
SketchContext   — dataclass: mode: Literal["dev", "build"]
SketchMeta      — dataclass: date, name, description

@step           — ContextVar proxy; direct call executes immediately
@sketch         — stamps __is_sketch__, __sketch_meta__ on the function
source(path, loader) -> Proxy
output(proxy, name, *, presets) -> Proxy

# core/protocol.py
SketchValueProtocol  — @runtime_checkable Protocol:
                         extension: str
                         to_bytes(mode: Literal["dev", "build"]) -> bytes
                         to_html(url: str) -> str   # optional; defaults to <img>

# core/building_dag.py  (runtime scratch pad during wiring)
Proxy           — step_id: str
StepCall        — step_id, fn, args (may contain Proxy), kwargs
SourceRecord    — step_id, path: Path, loader: Callable
OutputRecord    — step_id, source_proxy: Proxy, bundle_name: str, presets: list[str] | None
BuildingDAG     — records calls/sources/outputs; allocates IDs

# core/built_dag.py  (post-wiring, validated representation)
ParamSpec       — name, type, default, param: Param
InputSpec       — name, type, optional: bool
BuiltNode       — step_id, fn, source_ids: dict[str,str],
                  param_schema: list[ParamSpec], param_values: dict[str,Any],
                  ctx: SketchContext | None, output: Any
BuiltDAG        — nodes: dict[str, BuiltNode]  (insertion = topo order)
                  source_paths: list[tuple[Path, str]]
                  output_nodes: list[tuple[str, str, list[str]|None]]

# core/introspect.py
extract_inputs(fn) -> list[InputSpec]
extract_params(fn) -> list[ParamSpec]

# core/wiring.py
wire_sketch(fn, ctx: SketchContext) -> BuiltDAG

# core/executor.py  (additions alongside existing functions)
execute_built(dag: BuiltDAG, workdir: Path, mode: Literal["dev", "build"] = "dev") -> ExecutionResult
execute_partial_built(dag: BuiltDAG, start_ids: list[str], workdir: Path, mode: ...) -> ExecutionResult
```

---

## Increment 1: Walking Skeleton

### Acceptance test

> I define a sketch using `@sketch` and `@step`. I run `uv run dev`. I open the browser and
> see the step's output image. I overwrite the source asset on disk, and the browser updates
> without a manual refresh.

### What this drives

This is the thinnest possible slice that touches every new architectural boundary. No params,
no presets, no build output — just: wire → execute → serve → watch → re-execute → push.

**Protocol layer (new, additive):**
- `@step` — ContextVar proxy mechanism (from spike). Direct call executes; sketch-context call
  records and returns `Proxy`.
- `@sketch` — stamps `__is_sketch__` and `__sketch_meta__` on the function.
- `source(path, loader)` — records a `SourceRecord` in `BuildingDAG`, returns `Proxy`.
- `output(proxy, name)` — records an `OutputRecord` in `BuildingDAG`, returns `Proxy`.
- `Param` and `SketchContext` — defined but unused in this increment.
- `SketchValueProtocol` — the executor checks this to know how to write workdir files.

**DAG construction (new):**
- `BuildingDAG`, `Proxy`, `StepCall`, `SourceRecord`, `OutputRecord`.
- `wire_sketch(fn, ctx)` — runs the sketch function in a `building_sketch()` context, then
  converts `BuildingDAG` into a validated `BuiltDAG`. Validates that all proxy references
  resolve; raises `ValueError` with a clear message otherwise.
- `extract_inputs(fn)` — reads positional args from the function signature. Used by the wiring
  layer to populate `BuiltNode.source_ids`.
- No param extraction yet — steps in this increment have no keyword-only params.

**Execution (new, additive):**
- `execute_built(dag, workdir, mode="dev")` — walks `BuiltDAG` in topo order, gathers inputs
  from upstream outputs, calls `node.fn(**inputs)`, writes `node.output.to_bytes("dev")` to
  workdir. Primitive/non-protocol fallback: `str(result).encode()` as `.txt`.

**Discovery (additive):**
- `discover_sketch_fns(sketches_dir)` — scans submodules for callables with `__is_sketch__`.
  Added alongside existing `discover_sketches()`.

**Registry (new, alongside old):**
- `SketchFnRegistry` — holds `dict[str, Callable]` candidates and `dict[str, BuiltDAG]` loaded
  DAGs. Lazy-loads on first access: `wire_sketch` → `execute_built` → register watcher.
  Lives alongside the old `SketchRegistry`; new acceptance tests use a new fixture.

**Server (additive):**
- New routes served by the new registry alongside old routes so existing tests keep passing.
  For the skeleton, only what the acceptance test exercises:
  - `GET /sketch/{slug}` — renders sketch page showing the output node's image.
  - `GET /workdir/{slug}/{step_id}.{ext}` — serves the workdir file (extension now variable).
  - `WS /ws/{slug}` — pushes `step_updated` events.

**File watcher:**
- `SketchFnRegistry._register_watch` watches `dag.source_paths`. On change: calls
  `execute_partial_built(dag, [source_step_id], workdir, mode="dev")`, broadcasts results.

**Test infrastructure (new fixtures in conftest):**
- `fn_registry_client(tmp_fn_sketch)` — a `TestClient` wired to `SketchFnRegistry`.
- `tmp_fn_sketch` — creates a temp sketch directory with a `.png` test image.
- `TestImage` — defined in `tests/conftest.py`, satisfies `SketchValueProtocol`. Used by
  framework tests to avoid importing `sketches.*`.

### Test sketch for this increment

Defined in the test file (not in `sketches/`):

```python
@step
def passthrough(image: TestImage) -> TestImage:
    """Return the image unchanged."""
    return image

@sketch(date="2026-01-01")
def hello():
    """Simplest possible sketch."""
    img = source("assets/hello.png", loader=lambda p: TestImage.load(p))
    result = passthrough(img)
    output(result, "bundle")
```

### Acceptance test (pytest)

```python
# tests/acceptance/test_walking_skeleton_v3.py

def test_step_output_served_in_browser(tmp_fn_sketch, fn_registry_client):
    """A @sketch with one source and one @step shows the image in the browser."""
    response = fn_registry_client.get("/sketch/hello")
    assert response.status_code == 200
    img_url = extract_img_src(response.text)
    img_response = fn_registry_client.get(img_url)
    assert img_response.status_code == 200
    assert img_response.headers["content-type"].startswith("image/")

async def test_file_change_triggers_websocket_update(tmp_fn_sketch, fn_registry_client, ws_client):
    """Overwriting the source asset pushes step_updated over WebSocket."""
    async with ws_client("/ws/hello") as ws:
        write_test_image(tmp_fn_sketch / "assets" / "hello.png")
        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
        assert msg["type"] == "step_updated"
        assert "image_url" in msg
```

### Prior art

| File | Relationship | Notes |
|---|---|---|
| `core/executor.py` | Strong reference | `_execute_nodes`, `_gather_inputs`, `_delete_workdir`, failure propagation — all directly applicable to `execute_built`. Main difference: call convention changes from `step.process(inputs, params)` to `fn(**inputs, **params)`. |
| `core/dag.py` | Reference | Topo sort algorithm and `descendants()` BFS are identical; port to `BuiltDAG`. `DAGNode`/`DAG` themselves are superseded. |
| `core/watcher.py` | Reuse as-is | `Watcher` class is unchanged. `SketchFnRegistry` calls `watcher.watch(path, callback)` the same way `SketchRegistry` does. |
| `server/registry.py` | Strong reference | Lazy-load pattern, `threading.Lock` double-check, WebSocket `broadcast` / `broadcast_results`, watcher registration — all directly applicable to `SketchFnRegistry`. |
| `server/routes/ws.py` | Likely reusable | WebSocket endpoint logic is registry-agnostic if the registry exposes the same `connections` dict interface. |
| `server/routes/sketch.py` | Reference | Route structure and template rendering pattern. |
| `discovery.py` | Reference | `discover_sketches` scans submodules; `discover_sketch_fns` does the same but checks `__is_sketch__` attribute instead of `issubclass(obj, Sketch)`. |
| `steps/source.py` | Reference | `SourceFile` semantics (watched path + loader callable) are preserved in `source()`. |

### Definition of done — Increment 1

- [ ] `tests/acceptance/test_walking_skeleton_v3.py` passes
- [ ] `tests/unit/test_decorators.py` — `@step` direct call executes; sketch-context call returns
      `Proxy`; nested `building_sketch()` contexts are isolated; `@sketch` stamps attributes
- [ ] `tests/unit/test_building_dag.py` — proxy recording; ID collision resolution;
      `source()` / `output()` record into correct structures; ID isolation across contexts
- [ ] `tests/unit/test_introspect.py` — `extract_inputs` reads positional args; optional inputs
      (`T | None = None`) flagged correctly; `SketchContext` args excluded from inputs
- [ ] `tests/unit/test_wiring.py` — wire a two-step sketch; BuiltDAG has correct nodes and
      `source_ids`; disconnected required input raises `ValueError` at wire time
- [ ] `tests/unit/test_executor_v3.py` — full execution of minimal BuiltDAG; `SketchValueProtocol`
      value writes workdir file with `to_bytes("dev")`; primitive fallback writes `.txt`;
      upstream failure propagates; failed node's workdir file deleted
- [ ] `tests/unit/test_discovery.py` extended — `discover_sketch_fns` finds `__is_sketch__`
      callables; ignores non-decorated functions
- [ ] `tests/unit/test_protocol.py` — `SketchValueProtocol` structural check; class missing
      `to_bytes` fails; class without `to_html` passes (optional)
- [ ] All existing tests still pass
- [ ] `mise run lint` passes

---

## Increment 2: Tunable Parameters

### Acceptance test

> I define a `@step` with `Annotated[int, Param(min=1, max=20)]` keyword-only parameters.
> I open the sketch in the browser and see Tweakpane sliders. I drag a slider. The output
> image updates live.

### What this drives

**Introspection (addition to Increment 1):**
- `extract_params(fn)` — reads keyword-only args annotated with `Annotated[T, Param(...)]`.
  Returns `list[ParamSpec]`. Default values come from the function signature default.
- `wire_sketch` uses `extract_params` to populate `BuiltNode.param_schema` and initialize
  `BuiltNode.param_values` from defaults.
- Steps with no `Param` annotations are unaffected (backward compatible with Increment 1).

**Execution (addition):**
- `execute_built` passes `**node.param_values` alongside resolved inputs when calling the step.
- `execute_partial_built` — used for re-execution on param change.

**Param coercion:**
- `coerce_param(spec: ParamSpec, raw: Any) -> Any` — coerces a raw JSON value to the declared
  type. `bool` handling mirrors the current `_coerce_bool` in `core/params.py`. Lives in
  `core/introspect.py` or `core/params_v3.py`.

**Tweakpane adapter (addition):**
- `param_spec_to_tweakpane(spec: ParamSpec, current_value: Any) -> dict` — converts a
  `ParamSpec` + current value to the Tweakpane wire schema.
  Calls `current_value.to_tweakpane()` if present (hook for Color and similar types).
- `built_node_to_tweakpane(node: BuiltNode) -> dict[str, dict]` — all params for a node.

**Server (additions):**
- `GET /api/sketches/{slug}/params/{step_id}` — returns Tweakpane schema for a node's params.
- `PATCH /api/sketches/{slug}/params` — accepts `{step_id, param_name, value}`, coerces,
  updates `BuiltNode.param_values`, triggers `execute_partial_built`, broadcasts
  `step_updated` over WebSocket.
- Tweakpane panel in the sketch UI reads from the params endpoint and wires `onChange` to PATCH.

**SketchContext in steps:**
- A `@step` function can declare `ctx: SketchContext`. `extract_params` and `extract_inputs`
  both exclude it; `wire_sketch` stores the `SketchContext` on the node; the executor injects
  it at call time.

### Test sketch for this increment

```python
@step
def threshold_image(
    image: TestImage,
    *,
    level: Annotated[int, Param(min=0, max=255, step=1, debounce=150)] = 128,
) -> TestImage:
    """Threshold the image at the given level."""
    ...

@sketch(date="2026-01-01")
def threshold_hello():
    """Threshold sketch."""
    img = source("assets/hello.png", loader=lambda p: TestImage.load(p))
    result = threshold_image(img)
    output(result, "bundle")
```

### Acceptance test (pytest)

```python
# tests/acceptance/test_params_v3.py

def test_param_schema_endpoint(tmp_fn_sketch, fn_registry_client):
    """The param schema endpoint returns Tweakpane-compatible definitions."""
    response = fn_registry_client.get("/api/sketches/threshold_hello/params/threshold_image")
    schema = response.json()
    assert "level" in schema
    assert schema["level"]["min"] == 0
    assert schema["level"]["max"] == 255

async def test_param_change_triggers_websocket_update(tmp_fn_sketch, fn_registry_client, ws_client):
    """Changing a param via API triggers re-execution and a WebSocket step_updated message."""
    async with ws_client("/ws/threshold_hello") as ws:
        response = fn_registry_client.patch("/api/sketches/threshold_hello/params", json={
            "step_id": "threshold_image",
            "param_name": "level",
            "value": 64,
        })
        assert response.status_code == 200
        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
        assert msg["type"] == "step_updated"
        assert msg["step_id"] == "threshold_image"
```

### Prior art

| File | Relationship | Notes |
|---|---|---|
| `core/params.py` | Strong reference | `_coerce_bool` is directly reusable in `coerce_param`. `ParamDef` field names (`min`, `max`, `step`, `debounce`, `options`, `label`) map 1-to-1 to `Param`. `ParamRegistry.set_value` type coercion logic is the same algorithm. |
| `server/tweakpane.py` | Strong reference | `param_def_to_tweakpane()` → `param_spec_to_tweakpane()`. Same output shape; source changes from `ParamDef` to `ParamSpec`. `to_tweakpane()` duck-typing hook is already present. |
| `server/routes/params.py` | Strong reference | `ParamUpdate` Pydantic model, 404 handling, re-execute + broadcast pattern are identical. Replace `node.step.set_param(...)` with `coerce_param` + `node.param_values[name] = value`. |
| `tests/unit/test_params.py` | Reference | Coverage baseline: type coercion, bool string handling, options validation — all need equivalents in `test_introspect.py` or `test_params_v3.py`. |

### Definition of done — Increment 2

- [ ] `tests/acceptance/test_params_v3.py` passes
- [ ] `tests/unit/test_introspect.py` extended:
      `Annotated[int, Param(min=1)]` → `ParamSpec` with correct fields;
      `Annotated[float, Param(...)] = 0.5` → `ParamSpec` with `default=0.5`;
      bare `count: int` with no `Param` → `InputSpec` (not a param);
      `SketchContext` arg → excluded from both inputs and params;
      `T | None = None` with `Param` → optional param (valid)
- [ ] `tests/unit/test_wiring.py` extended — step with params → `BuiltNode.param_schema` and
      `param_values` populated from defaults; `SketchContext` stored on `BuiltNode`
- [ ] `tests/unit/test_executor_v3.py` extended — `param_values` passed as kwargs to step fn;
      updated param value flows through re-execution; ctx injected when declared
- [ ] `tests/unit/test_tweakpane_v3.py` — `param_spec_to_tweakpane` produces correct schema
      for `int`, `float`, `bool`, `str`; `to_tweakpane()` called on rich values if present
- [ ] All existing tests still pass
- [ ] `mise run lint` passes

---

## Increment 3: Preset Persistence

### Acceptance test

> I tweak params in the browser. The values persist in `_active.json`. I save a named preset.
> I change params (UI shows dirty indicator). I load the preset back and the params snap to the
> saved values. I reload the page and my active params are still there.

### What this drives

The preset file format is unchanged: `{ "step_id": { "param_name": value, ... } }`. Step IDs
now use the new naming convention (function names, no `_0` suffix), but the file structure is
identical.

**Preset I/O for BuiltDAG (additions to `core/presets.py`):**
- `load_active_into_built(dag, presets_dir) -> tuple[bool, str | None]`
  — reads `_active.json`, applies values to `BuiltNode.param_values`. Returns `(dirty, based_on)`.
- `save_active_from_built(dag, presets_dir, dirty, based_on)` — serializes `param_values`
  to `_active.json`.
- `load_preset_into_built(dag, presets_dir, name)` — reads `<name>.json`, applies to
  `param_values`. Does not write to disk (caller handles `save_active`).
- `save_preset_from_built(dag, presets_dir, name)` — snapshots current `param_values` to
  `<name>.json`.

These live alongside the existing `PresetManager` methods, which are unchanged.

**Registry (addition):**
- `SketchFnRegistry` lazy-load sequence now includes `load_active_into_built` after wiring.
- `set_param` now also calls `save_active_from_built(dirty=True)` after updating `param_values`.

**Server (additions):**
- `GET /api/sketches/{slug}/presets` — list named presets + active state `{dirty, based_on}`.
- `POST /api/sketches/{slug}/presets` — save current as `{name}`.
- `POST /api/sketches/{slug}/presets/{name}/load` — load preset, re-execute, broadcast.
- `POST /api/sketches/{slug}/presets/new` — reset to defaults, re-execute, broadcast.
- Frontend preset toolbar: dropdown, save/save-as buttons, dirty indicator (`*`).

### Acceptance test (pytest)

```python
# tests/acceptance/test_presets_v3.py

def test_preset_save_load_cycle(tmp_fn_sketch, fn_registry_client):
    """Save a preset, change params, load it back — params restore."""
    fn_registry_client.patch("/api/sketches/threshold_hello/params", json={
        "step_id": "threshold_image", "param_name": "level", "value": 42,
    })
    fn_registry_client.post("/api/sketches/threshold_hello/presets", json={"name": "low"})
    assert (tmp_fn_sketch / "presets" / "low.json").exists()

    fn_registry_client.patch("/api/sketches/threshold_hello/params", json={
        "step_id": "threshold_image", "param_name": "level", "value": 200,
    })
    fn_registry_client.post("/api/sketches/threshold_hello/presets/low/load")

    schema = fn_registry_client.get(
        "/api/sketches/threshold_hello/params/threshold_image"
    ).json()
    assert schema["level"]["value"] == 42

def test_active_json_written_on_param_change(tmp_fn_sketch, fn_registry_client):
    """Editing a param writes _active.json with dirty=True."""
    fn_registry_client.patch("/api/sketches/threshold_hello/params", json={
        "step_id": "threshold_image", "param_name": "level", "value": 99,
    })
    active = json.loads((tmp_fn_sketch / "presets" / "_active.json").read_text())
    assert active["_meta"]["dirty"] is True
    assert active["threshold_image"]["level"] == 99

def test_params_restored_on_reload(tmp_fn_sketch, fn_registry_client):
    """Active params persisted in _active.json survive a registry reload."""
    fn_registry_client.patch("/api/sketches/threshold_hello/params", json={
        "step_id": "threshold_image", "param_name": "level", "value": 77,
    })
    fn_registry_client.app.state.registry.evict("threshold_hello")
    schema = fn_registry_client.get(
        "/api/sketches/threshold_hello/params/threshold_image"
    ).json()
    assert schema["level"]["value"] == 77
```

### Prior art

| File | Relationship | Notes |
|---|---|---|
| `core/presets.py` | Strong reference | `_Encoder` (Color JSON serialization) is reusable as-is. `_snapshot_params` is the model for the new snapshot: iterates nodes, collects param values. Dirty/`based_on` tracking logic and the `_meta` JSON wrapper format are identical. `load_active` and `save_active` are the direct precedents for the new `*_into_built` / `*_from_built` variants. |
| `server/routes/presets.py` | Strong reference | All four route handlers (`list_presets`, `save_preset`, `new_preset`, `load_preset`) are directly applicable. Replace `sketch.preset_manager.*` calls with the new `*_from_built` / `*_into_built` helpers and `BuiltNode.param_values`. Error handling and broadcast pattern are identical. |
| `tests/unit/test_presets.py` | Reference | Coverage baseline for the new preset tests: save/load round-trip, dirty flag, `based_on` tracking, missing file handling. |

### Definition of done — Increment 3

- [ ] `tests/acceptance/test_presets_v3.py` passes
- [ ] `tests/unit/test_presets_v3.py`:
      `load_active_into_built` applies values from JSON to `param_values`;
      `save_active_from_built` writes correct JSON including `_meta`;
      `load_preset_into_built` applies named preset without writing disk;
      `save_preset_from_built` writes named file;
      missing `_active.json` is a no-op (defaults stay)
- [ ] All existing tests still pass
- [ ] `mise run lint` passes

---

## Increment 4: Site Build

### Acceptance test

> I run `uv run build`. The `dist/` directory contains `manifest.json` and baked image files.
> Each image is rendered at build quality (via `to_bytes("build")`). A sketch that declares
> `SketchContext` in a step behaves differently in build mode than in dev mode.

### What this drives

**`to_bytes(mode)` in execution:**
- `execute_built(dag, workdir, mode)` already accepts `mode`. In `"build"` mode it calls
  `node.output.to_bytes("build")`; in `"dev"` mode, `to_bytes("dev")`. No separate function.
- `TestImage.to_bytes("dev")` — fast path (low quality). `TestImage.to_bytes("build")` — slow
  path (high quality). The acceptance test verifies the two outputs differ.

**SketchContext in steps:**
- A `@step` function can declare `ctx: SketchContext` as an argument.
- `wire_sketch` stores the `SketchContext` on each `BuiltNode` whose function requests it.
- The executor injects it: `fn(**inputs, ctx=node.ctx, **params)`.
- This is how steps implement dev vs build behavior without a `Postprocess` step.

**Builder:**
- `build_bundle_fns(sketch_fns, sketches_dir, output_dir, bundle_name, workers)` in
  `bundle/builder.py`, alongside existing `build_bundle`.
- Phase 1 (discovery): wire each sketch with `SketchContext(mode="build")`. Find output nodes
  matching `bundle_name`. Resolve preset list. Skip if no output nodes or no presets.
- Phase 2 (execution, parallel): for each (sketch, preset) pair — wire fresh BuiltDAG,
  `load_preset_into_built`, `execute_built(dag, tmp_workdir, mode="build")`. Write
  `output_node.output.to_bytes("build")` + `extension` to `output_dir/{slug}/{preset}.{ext}`.
- Phase 3 (manifest): assemble `manifest.json`. Same structure as today.

**CLI:**
- `cli.py` `build` command updated to call `discover_sketch_fns` + `build_bundle_fns`.

### Test sketch for this increment

```python
@step
def scale_factor(ctx: SketchContext) -> float:
    """Return 0.25 in dev, 1.0 in build."""
    return 0.25 if ctx.mode == "dev" else 1.0

@step
def resize(image: TestImage, scale: float) -> TestImage:
    """Resize image by scale."""
    ...

@sketch(date="2026-01-01")
def build_demo():
    """Sketch that produces different output in dev vs build."""
    img = source("assets/hello.png", loader=lambda p: TestImage.load(p))
    scale = scale_factor()
    result = resize(img, scale)
    output(result, "bundle", presets=["default"])
```

`scale_factor()` is called with no positional args in the sketch body — its only input is
the injected `SketchContext`. Its result (a float `Proxy`) is passed as a positional arg to
`resize`. Both patterns are tested here: a context-only step, and a step receiving a scalar
proxy.

### Acceptance test (pytest)

```python
# tests/acceptance/test_static_site_v3.py

def test_build_produces_manifest_and_images(tmp_fn_sketch_with_preset, tmp_output_dir):
    """build_bundle_fns writes manifest.json and baked images."""
    build_bundle_fns(
        sketch_fns={"build_demo": build_demo},
        sketches_dir=tmp_fn_sketch_with_preset.parent,
        output_dir=tmp_output_dir,
        bundle_name="bundle",
    )
    manifest = json.loads((tmp_output_dir / "manifest.json").read_text())
    assert len(manifest) == 1
    entry = manifest[0]
    assert entry["slug"] == "build-demo"
    assert len(entry["variants"]) == 1
    image_path = tmp_output_dir / entry["variants"][0]["image_path"]
    assert image_path.exists() and image_path.stat().st_size > 0

def test_build_uses_build_mode_bytes(tmp_fn_sketch_with_preset, tmp_output_dir):
    """Baked images use to_bytes('build'), distinguishable from to_bytes('dev')."""
    build_bundle_fns(...)
    source_img = TestImage.load(source_path)
    built_bytes = (tmp_output_dir / "build-demo" / "default.png").read_bytes()
    dev_bytes = source_img.to_bytes("dev")
    assert built_bytes != dev_bytes

def test_sketch_context_mode_in_build(tmp_fn_sketch_with_preset, tmp_output_dir):
    """Steps that declare SketchContext receive mode='build' during build."""
    build_bundle_fns(...)
    img = load_test_image(tmp_output_dir / "build-demo" / "default.png")
    source_img = TestImage.load(source_path)
    # scale_factor returns 1.0 in build → full size, not 0.25x
    assert img.width == source_img.width
```

### Prior art

| File | Relationship | Notes |
|---|---|---|
| `bundle/builder.py` | Strong reference | Three-phase structure (discovery → parallel execution → manifest) is identical. `_VariantTask`, `_VariantResult`, `_DiscoveryResult` dataclasses are directly applicable. `ThreadPoolExecutor` + `as_completed` pattern is reusable. Phase 3 manifest assembly is unchanged. Replace `sketch_cls(sketch_dir, mode="build")` + `execute(sketch.dag)` with `wire_sketch(fn, ctx)` + `execute_built(dag, workdir, mode="build")`. |
| `steps/output_bundle.py` | Reference | `OutputBundle.bundle_name` and `OutputBundle.presets` filtering logic maps to `BuiltDAG.output_nodes`. The builder's node-scanning loop is the model. |
| `core/types.py` | Reference | `Image.to_bytes()` with `compress_level` is the model for `to_bytes(mode)` — the new `Image` in `sketches/types.py` uses `compress_level=0` for `"dev"` and `compress_level=9` for `"build"`. |
| `tests/acceptance/test_static_site.py` | Reference | Coverage baseline: existing test shows what the manifest structure must look like and what assertions matter for build correctness. |

### Definition of done — Increment 4

- [ ] `tests/acceptance/test_static_site_v3.py` passes
- [ ] `tests/unit/test_executor_v3.py` extended — `mode="build"` calls `to_bytes("build")`;
      `mode="dev"` calls `to_bytes("dev")`; ctx injected for steps that declare it;
      `scale_factor()` (no-input step) executes and its float output flows downstream
- [ ] `tests/unit/test_wiring.py` extended — step with `ctx: SketchContext` gets context
      stored in `BuiltNode`; scalar float proxy flows through as pipeline input to `resize`
- [ ] `tests/unit/test_builder_v3.py` — `build_bundle_fns` skips sketches with no output
      nodes; skips sketches with no presets; parallel execution produces correct outputs;
      preset filtering (`presets=["name"]`) honoured
- [ ] CLI `build` command uses `discover_sketch_fns` + `build_bundle_fns`
- [ ] All existing tests still pass
- [ ] `mise run lint` passes

---

## Increment 5: Sketch Cutover

### Acceptance test

> All four existing sketches load in the dev server using the new API. `uv run build` produces
> a valid site bundle. The framework source contains no references to `PipelineStep`, `Sketch`,
> `DAGNode`, or `DAG`. `mise run lint` passes.

### What this drives

**`sketches/types.py` (new file):**
- `Image` — wraps numpy array. Satisfies `SketchValueProtocol`:
  - `extension = "png"`
  - `to_bytes(mode)` — `compress_level=0` for `"dev"`, `compress_level=9` for `"build"`
  - `to_html(url)` — `<img src="{url}">`
  - `load(path: Path) -> Image` — static method, replaces the `cv2.imread` lambdas
- `Color` — moved from `framework/src/sketchbook/core/params.py`. Keeps `to_tweakpane()`.

**Sketch ports (one at a time, in order):**

1. `sketches/cardboard/__init__.py` — `CircleGridMask`, `DifferenceBlend` become `@step`
   functions. `Cardboard(Sketch)` becomes `@sketch def cardboard()`. `Postprocess` deleted.
2. `sketches/cardboard_stripes/__init__.py` — same pattern. `StripesMask`, `DifferenceBlend`
   become `@step` functions. `DifferenceBlend` duplicated from cardboard — intentional.
3. `sketches/fence-torn-paper/__init__.py` — `GaussianBlur`, `CannyEdge`, `CannyComposite`
   become `@step` functions. `Color` imported from `sketches.types`.
4. `sketches/kick-polygons/__init__.py` — `Downscale` scale factor becomes a `@step` function
   returning `float` driven by `SketchContext`. `RadialArrange` becomes a `@step` function.

**Preset file migration:**

Current step ID format: `circle_grid_mask_0` (class snake_case + always `_N` suffix)
New step ID format: `circle_grid_mask` (function name, no suffix for first occurrence)

Current source node format: `source_photo_0`
New source node format: `source_cardboard` (path stem, `source_` prefix)

Each sketch has ≤ 10 preset files. Rename keys by hand or with a one-shot script run once
and discarded. Not part of the framework.

**Route prefix dropped (flag day):**
- `server/routes/v3.py` router prefix changes from `/v3` to `/` — all routes become canonical.
- All hardcoded `/v3/...` URL strings inside the router (workdir URLs, WebSocket push payloads,
  `url_prefix` template context) updated to drop the prefix.
- Old `server/routes/sketch.py`, `params.py`, `presets.py`, `ws.py` (the v1 routes) deleted.
- `server/app.py` updated: include only `v3.router`, remove old router includes.
- Acceptance test `test_all_sketches_load_in_dev_server` hits `/sketch/{slug}` (no prefix) to
  verify the routes landed at root.

**CLI wired up:**
- `cli.py` `dev` command: `discover_sketch_fns` + `SketchFnRegistry`. Old path removed.
- `cli.py` `build` command: already updated in Increment 4.

**Old code deleted:**
```
framework/src/sketchbook/core/step.py
framework/src/sketchbook/core/sketch.py
framework/src/sketchbook/core/types.py
framework/src/sketchbook/core/dag.py          (DAGNode, DAG — not BuiltDAG)
framework/src/sketchbook/steps/source.py
framework/src/sketchbook/steps/output_bundle.py
framework/src/sketchbook/steps/site_output.py  (if present)
framework/src/sketchbook/steps/__init__.py      (if now empty)
```

Old parts of `params.py` deleted: `ParamDef`, `ParamRegistry`, `_coerce_bool` (if superseded
by `coerce_param`), `Color` (moved). `params.py` may become empty or be deleted entirely.

Old tests deleted or retired:
```
tests/unit/test_step.py       → superseded by test_decorators.py
tests/unit/test_sketch.py     → superseded by test_wiring.py
tests/unit/test_dag.py        → superseded (BuiltDAG covered by test_built_dag.py)
tests/unit/test_types.py      → Image now in sketches/types.py; framework has no types
tests/unit/test_source.py     → SourceFile gone
tests/steps.py                → replaced with @step test functions in conftest/helpers
```

### Acceptance test (pytest)

```python
# tests/acceptance/test_cutover.py

def test_no_old_framework_symbols():
    """The framework source contains no references to PipelineStep, Sketch, or DAGNode."""
    framework_src = Path("framework/src/sketchbook")
    forbidden = {"PipelineStep", "from sketchbook.core.sketch", "DAGNode"}
    for py_file in framework_src.rglob("*.py"):
        text = py_file.read_text()
        for term in forbidden:
            assert term not in text, f"Found '{term}' in {py_file}"

def test_all_sketches_load_in_dev_server(sketches_dir, fn_registry_client_real):
    """All four real sketches wire and execute without error."""
    for slug in ["cardboard", "cardboard-stripes", "fence-torn-paper", "kick-polygons"]:
        response = fn_registry_client_real.get(f"/sketch/{slug}")
        assert response.status_code == 200, f"{slug} failed: {response.text}"

def test_build_produces_valid_site(sketches_dir, tmp_output_dir):
    """build_bundle_fns produces a manifest with all four sketches."""
    sketch_fns = discover_sketch_fns(sketches_dir)
    build_bundle_fns(sketch_fns, sketches_dir, tmp_output_dir, "bundle")
    manifest = json.loads((tmp_output_dir / "manifest.json").read_text())
    slugs = {e["slug"] for e in manifest}
    assert "cardboard" in slugs
    assert "kick-polygons" in slugs
```

### Prior art

| File | Relationship | Notes |
|---|---|---|
| `core/types.py` | Port | `Image` class moves to `sketches/types.py`. `to_bytes()` becomes `to_bytes(mode)`. `PipelineValue` ABC is deleted (replaced by `SketchValueProtocol`). PIL encoding logic is unchanged. |
| `core/params.py` | Port | `Color` class (including `to_tweakpane()`, hex parsing, `__str__`) moves to `sketches/types.py` verbatim. |
| `sketches/cardboard/__init__.py` | Direct reference | Each `PipelineStep` subclass becomes a `@step` function. `setup()` inputs/params become function signature. `process(inputs, params)` body becomes function body — `inputs["image"]` becomes `image`, `params["count"]` becomes `count`. `Postprocess` deleted. |
| `sketches/cardboard_stripes/__init__.py` | Direct reference | Same pattern. `_WIDTH_FNS` dict and `_lerp` helper stay as module-level helpers unchanged. |
| `sketches/fence-torn-paper/__init__.py` | Direct reference | Same pattern. `Color` param annotation: `color: Annotated[Color, Param(debounce=150)] = Color("#ff69b4")`. |
| `sketches/kick-polygons/__init__.py` | Direct reference | `Downscale.__init__(scale)` construction-time branching becomes a `@step def downscale_factor(ctx: SketchContext) -> float`. `RadialArrange.process` body is unchanged content-wise. |

### Definition of done — Increment 5

- [ ] `tests/acceptance/test_cutover.py` passes
- [ ] `tests/acceptance/test_walking_skeleton_v3.py` still passes
- [ ] `tests/acceptance/test_params_v3.py` still passes
- [ ] `tests/acceptance/test_presets_v3.py` still passes
- [ ] `tests/acceptance/test_static_site_v3.py` still passes
- [ ] Zero imports of `PipelineStep`, `Sketch`, `DAGNode`, `DAG` anywhere in `framework/`
- [ ] Zero imports from `sketches.*` anywhere in `framework/`
- [ ] `uv run dev` starts cleanly; all four sketches load and show output
- [ ] `uv run build` completes; `dist/manifest.json` contains all four sketches
- [ ] All v3 routes served at root (no `/v3` prefix); old route files deleted
- [ ] `mise run lint` passes with zero violations

---

## What each increment leaves working

| After increment | uv run dev | uv run build | Real sketches |
|---|---|---|---|
| 1 (Walking skeleton) | test sketch only (new path) | unchanged | old API |
| 2 (Parameters) | test sketch + params | unchanged | old API |
| 3 (Presets) | test sketch + params + presets | unchanged | old API |
| 4 (Site build) | test sketch | new builder wired | old API |
| 5 (Cutover) | all four real sketches | all four real sketches | new API |
