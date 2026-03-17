# Sketchbook — Implementation Plan

## Overview

Sketchbook is a reactive, DAG-based creative coding environment for image processing pipelines. Sketches are Python classes that define pipelines of transformations on source assets (primarily photos). In dev mode, a FastAPI server watches source files and propagates changes through the pipeline in real time, with every intermediate step inspectable in the browser. The system also supports static site generation for publishing finished work.

This plan follows the "Growing Object-Oriented Software, Guided by Tests" approach. Instead of building layer by layer (engine → params → server → UI), we grow the system end-to-end from a walking skeleton. Each increment is defined by an acceptance test that drives implementation across all layers simultaneously.

## Decisions Log

| Decision | Choice |
|---|---|
| Web framework | FastAPI (async, WebSocket-native) |
| Frontend | Server-rendered HTML (Jinja2) + Tweakpane + minimal JS |
| DAG visualization | Pure HTML/CSS hierarchical layout |
| File watching | watchdog, per source node (single file each) |
| Sketch concurrency | Multiple loaded, one active/watched at a time |
| Step authoring | Class-based (`PipelineStep` subclasses) |
| Pipeline wiring | Both fluent chaining and explicit named-input wiring |
| Presets | Per-step, JSON-backed, with dirty/untitled draft semantics |
| Static site | Feed → sketch pages, with variant support (preset-based) |
| Intermediates | `.workdir/` per sketch module, `.gitignore`d |
| Caching | Full re-run for now; revisit later |
| CLI | `uv` scripts |
| Project structure | Convention-based, each sketch is a Python module with its own assets |
| Deployment | Build locally, push built output to `gh-pages` branch |

---

## Project Structure

```
sketchbook/
├── pyproject.toml
├── .mise.toml
├── .gitignore
├── CLAUDE.md
├── src/
│   └── sketchbook/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── dag.py              # DAG graph, node types, topology sort, change propagation
│       │   ├── step.py             # PipelineStep base class
│       │   ├── sketch.py           # Sketch base class with build() DSL
│       │   ├── params.py           # Parameter definitions, preset load/save/dirty tracking
│       │   ├── watcher.py          # watchdog integration, per-source-node file monitoring
│       │   ├── executor.py         # Pipeline execution engine (run DAG in topo order)
│       │   └── types.py            # Shared types (Image wrapper, etc.)
│       ├── server/
│       │   ├── __init__.py
│       │   ├── app.py              # FastAPI app, route registration
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   ├── sketch.py       # Sketch list, sketch detail, step detail views
│       │   │   ├── params.py       # Preset CRUD API, Tweakpane data endpoints
│       │   │   ├── dag.py          # DAG overview page
│       │   │   └── ws.py           # WebSocket endpoint for live updates
│       │   ├── templates/
│       │   │   ├── base.html
│       │   │   ├── index.html      # Sketch browser/list
│       │   │   ├── sketch.html     # Single sketch: DAG + params + preview
│       │   │   ├── step.html       # Fullscreen step output view
│       │   │   └── dag.html        # DAG overview component
│       │   └── static/
│       │       ├── main.js         # WebSocket client, Tweakpane init, live reload
│       │       └── style.css
│       ├── steps/
│       │   ├── __init__.py
│       │   ├── source.py           # SourceFile node (reads image from disk)
│       │   ├── output.py           # FileOutput node (writes to disk)
│       │   ├── site_output.py      # StaticSiteOutput node (registers for site build)
│       │   └── opencv/
│       │       ├── __init__.py
│       │       ├── edge_detect.py  # Canny edge detection example step
│       │       └── blur.py         # Gaussian blur example step
│       ├── site/
│       │   ├── __init__.py
│       │   ├── builder.py          # Scans sketches for SiteOutput nodes, generates static site
│       │   └── templates/
│       │       ├── feed.html       # Main feed page
│       │       └── sketch_page.html # Individual sketch + variants page
│       ├── cli.py                  # Entry points for `uv run dev` and `uv run build`
│       └── sketches/               # User sketch modules (convention-based)
│           └── edge_portrait/
│               ├── __init__.py     # Contains the Sketch subclass
│               ├── assets/
│               │   ├── portrait.jpg
│               │   └── mask.png
│               ├── presets/
│               │   ├── heavy_edges.json
│               │   └── _active.json  # Current working state (may be unsaved "untitled")
│               └── .workdir/       # Intermediate outputs, gitignored
│                   ├── edge_detect_out.png
│                   └── ...
├── tests/
│   ├── conftest.py                 # Shared fixtures (tmp sketch dirs, test images, FastAPI TestClient)
│   ├── acceptance/                 # End-to-end acceptance tests (one per increment)
│   │   ├── test_01_walking_skeleton.py
│   │   ├── test_02_real_step.py
│   │   ├── ...
│   └── unit/                       # Focused unit tests driven out by acceptance tests
│       ├── test_dag.py
│       ├── test_executor.py
│       ├── test_params.py
│       └── ...
└── dist/                           # Built static site output
    ├── index.html
    ├── edge-portrait/
    │   ├── index.html
    │   └── variants/
    │       ├── heavy_edges.png
    │       └── ...
    └── assets/                     # Baked images
```

---

## Increment 1: Walking Skeleton

### Acceptance test

> I define a sketch with one source node and one passthrough step. I run `uv run dev`. I open the browser and see the step's output image. I overwrite the source image on disk, and the browser updates without a manual refresh.

### What this drives

This is the thinnest possible slice that touches every architectural boundary:

**Core engine (just enough to work):**

- `PipelineStep` base class — only needs `setup()` and `process()`, with `add_input()`. No params yet.
- `Passthrough` step — takes an image input, returns it unchanged. The simplest possible real step.
- `SourceFile` step — reads an image from disk.
- `DAG` — holds nodes and edges. `add_node()`, `connect()`, `topo_sort()`. No `descendants()` yet (only two nodes, we re-run everything).
- `Sketch` base class — `source()` and `.pipe()` work. No `add()`, `output()`, or `site_output()` yet.
- `Image` type — wraps a numpy array. `Image.load(path)` and `.save(path)`.
- Executor — walks topo-sorted nodes, runs each, writes output to `.workdir/`.

**Server (just enough to show something):**

- FastAPI app with one route: `GET /sketch/{sketch_id}/step/{step_id}` serves a page with an `<img>` tag pointing at the `.workdir/` output.
- Static file serving for `.workdir/` images.
- WebSocket endpoint (`WS /ws/{sketch_id}`) that pushes `step_updated` events.
- Minimal `step.html` template: an image tag and a few lines of JS to connect the WebSocket and swap the `src` on update.

**File watcher:**

- watchdog watches the source node's file path.
- On change: re-execute the full DAG, push `step_updated` over WebSocket.

**CLI:**

- `uv run dev` starts the server, discovers the test sketch, builds its DAG, starts watchers.

### Test sketch for this increment

```python
# src/sketchbook/sketches/hello/__init__.py
from sketchbook import Sketch
from sketchbook.steps import Passthrough

class Hello(Sketch):
    name = "Hello"
    description = "Simplest possible sketch."
    date = "2026-03-16"

    def build(self):
        photo = self.source("photo", "assets/hello.jpg")
        photo.pipe(Passthrough)
```

### Acceptance test (pytest)

```python
# tests/acceptance/test_01_walking_skeleton.py

async def test_source_to_passthrough_shows_in_browser(tmp_sketch, test_client, ws_client):
    """A sketch with one source and one passthrough step shows the image in the browser."""
    # tmp_sketch creates a sketch dir with a test image at assets/hello.jpg
    # test_client is FastAPI TestClient

    # The step page returns HTML with an <img> tag
    response = test_client.get("/sketch/hello/step/passthrough_0")
    assert response.status_code == 200
    assert '<img' in response.text

    # The image URL resolves to actual image bytes
    img_url = extract_img_src(response.text)
    img_response = test_client.get(img_url)
    assert img_response.status_code == 200
    assert img_response.headers["content-type"].startswith("image/")

async def test_file_change_triggers_websocket_update(tmp_sketch, test_client, ws_client):
    """Overwriting the source image pushes an update over WebSocket."""
    # Connect WebSocket
    async with ws_client("/ws/hello") as ws:
        # Overwrite the source image
        write_test_image(tmp_sketch / "assets" / "hello.jpg", color="red")

        # Should receive a step_updated message
        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
        assert msg["type"] == "step_updated"
        assert "image_url" in msg
```

### Definition of done — Increment 1

- [x] Acceptance tests in `tests/acceptance/test_01_walking_skeleton.py` pass
- [ ] `tests/unit/test_dag.py` covers `DAG.add_node`, `connect`, `topo_sort`, cycle detection, duplicate node error
- [ ] `tests/unit/test_executor.py` covers full execution, failure propagation, workdir write, stale file deletion
- [ ] `tests/unit/test_step.py` covers `PipelineStep.add_input`, `setup`/`process` contract, `Passthrough` output equals input
- [ ] `tests/unit/test_types.py` covers `Image.load`, `Image.save`, round-trip integrity
- [ ] `tests/unit/test_sketch.py` covers `Sketch.source`, `.pipe`, DAG wiring, node ID assignment

---

## Increment 2: A Real Step With Parameters

### Acceptance test

> I define a sketch using Canny edge detection with `threshold1` and `threshold2` parameters. I open the step in the browser and see the edge-detected image. A Tweakpane panel shows two sliders. I drag a slider, and the image updates live.

### What this drives

**Core engine additions:**

- `add_param()` on `PipelineStep`. Param definitions with type, default, min, max, step.
- `ParamRegistry` — holds param definitions and current values for a step. Serializes to/from dict.
- Executor now gathers params and passes them to `process()`.
- `EdgeDetect` step — first real OpenCV step.

**Server additions:**

- `GET /api/sketches/{sketch_id}/params/{step_id}` — returns param schema + current values as JSON.
- `PATCH /api/sketches/{sketch_id}/params` — accepts `{step_id, param_name, value}`, updates in-memory state, triggers re-execution, pushes `step_updated` over WebSocket.
- `step.html` now includes a `<div>` for Tweakpane and loads Tweakpane from CDN.
- `main.js` initializes Tweakpane from the schema endpoint, wires `onChange` to PATCH the API.

**What stays thin:**

- No preset persistence yet — params live in memory only. Defaults come from step definitions.
- No DAG overview page yet — still just the single step view.

### Test sketch

```python
class EdgeHello(Sketch):
    name = "Edge Hello"

    def build(self):
        photo = self.source("photo", "assets/hello.jpg")
        photo.pipe(EdgeDetect)
```

### Acceptance test (pytest)

```python
async def test_param_change_updates_output(tmp_sketch, test_client, ws_client):
    """Changing a param via API triggers re-execution and WebSocket update."""
    async with ws_client("/ws/edge_hello") as ws:
        # Change threshold1
        response = test_client.patch("/api/sketches/edge_hello/params", json={
            "step_id": "edge_detect_0",
            "param_name": "threshold1",
            "value": 50.0,
        })
        assert response.status_code == 200

        # Should receive update
        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
        assert msg["type"] == "step_updated"
        assert msg["step_id"] == "edge_detect_0"

def test_param_schema_endpoint(tmp_sketch, test_client):
    """The param schema endpoint returns Tweakpane-compatible definitions."""
    response = test_client.get("/api/sketches/edge_hello/params/edge_detect_0")
    schema = response.json()
    assert "threshold1" in schema["params"]
    assert schema["params"]["threshold1"]["min"] == 0
    assert schema["params"]["threshold1"]["max"] == 500
```

### Definition of done — Increment 2

- [ ] Acceptance tests in `tests/acceptance/test_02_real_step.py` pass
- [ ] `tests/unit/test_params.py` covers `ParamRegistry.add`, default values, type coercion, serialization to/from dict, min/max constraints
- [ ] `tests/unit/test_step.py` updated: `add_param` registers in registry, params passed to `process()`
- [ ] `tests/unit/test_executor.py` updated: executor gathers params from registry and passes them to `process()`
- [ ] `tests/unit/test_edge_detect.py` covers `EdgeDetect.setup` declares correct params, `process` returns an image of the same shape

---

## Increment 3: Preset Persistence

### Acceptance test

> I tweak params in the browser. The values persist to `_active.json` on disk. I save a named preset. I change the params (UI shows "untitled*"). I load the saved preset and the params snap back. I reload the page and my active params are still there.

### What this drives

**Core engine additions:**

- `_active.json` read/write. On sketch load, read from disk (or generate defaults).
- Preset save: copy `_active.json` to `<n>.json`.
- Preset load: copy `<n>.json` to `_active.json`, update in-memory state, re-execute.
- Dirty tracking: `_meta.based_on` and `_meta.dirty` in the JSON wrapper.

**Server additions:**

- `GET /api/sketches/{sketch_id}/presets` — list preset files.
- `POST /api/sketches/{sketch_id}/presets` — save current as named preset.
- `POST /api/sketches/{sketch_id}/presets/{name}/load` — load preset.
- PATCH endpoint now writes to `_active.json` and sets dirty flag.
- `preset_state` WebSocket event.
- Frontend: preset `<select>` dropdown, save/save-as buttons, dirty indicator ("untitled*").

### Acceptance test (pytest)

```python
def test_preset_save_load_cycle(tmp_sketch, test_client):
    """Save a preset, change params, load it back — params restore."""
    # Tweak a param
    test_client.patch("/api/sketches/edge_hello/params", json={
        "step_id": "edge_detect_0",
        "param_name": "threshold1",
        "value": 42.0,
    })

    # Save as "low_thresh"
    test_client.post("/api/sketches/edge_hello/presets", json={"name": "low_thresh"})
    assert (tmp_sketch / "presets" / "low_thresh.json").exists()

    # Change param again
    test_client.patch("/api/sketches/edge_hello/params", json={
        "step_id": "edge_detect_0",
        "param_name": "threshold1",
        "value": 999.0,
    })

    # Load "low_thresh"
    test_client.post("/api/sketches/edge_hello/presets/low_thresh/load")

    # Params should be restored
    schema = test_client.get("/api/sketches/edge_hello/params/edge_detect_0").json()
    assert schema["params"]["threshold1"]["value"] == 42.0

def test_dirty_tracking(tmp_sketch, test_client):
    """Editing a loaded preset marks it dirty."""
    test_client.post("/api/sketches/edge_hello/presets", json={"name": "clean"})
    test_client.post("/api/sketches/edge_hello/presets/clean/load")

    # Should be clean
    presets = test_client.get("/api/sketches/edge_hello/presets").json()
    assert presets["active"]["dirty"] is False

    # Edit a param
    test_client.patch("/api/sketches/edge_hello/params", json={
        "step_id": "edge_detect_0",
        "param_name": "threshold1",
        "value": 1.0,
    })

    # Should be dirty
    presets = test_client.get("/api/sketches/edge_hello/presets").json()
    assert presets["active"]["dirty"] is True
```

### Definition of done — Increment 3

- [ ] Acceptance tests in `tests/acceptance/test_03_preset_persistence.py` pass
- [ ] `tests/unit/test_params.py` updated: `_active.json` round-trip, dirty flag set on edit, `based_on` written on load
- [ ] `tests/unit/test_presets.py` covers preset save (copies active to named file), preset load (replaces active, clears dirty), list returns all named presets

---

## Increment 4: DAG Overview and Multi-Step Pipelines

### Acceptance test

> I define a sketch with a source, a blur step, and an edge detect step chained together. I open the sketch page and see the DAG rendered as a tree. Each node is a link that opens the step's output in a new tab. The Tweakpane panel shows folders for both steps.

### What this drives

**Core engine additions:**

- `GaussianBlur` step — second real step, validates multi-step pipelines.
- DAG with 3+ nodes, topo sort over a real chain.
- `Sketch.add()` for explicit wiring (the blur→edge chain uses `.pipe()`, but we validate `add()` works too).

**Server additions:**

- `GET /sketch/{sketch_id}` — the sketch overview page. Renders the DAG and Tweakpane.
- `GET /api/sketches/{sketch_id}/dag` — DAG structure as JSON (nodes, edges, step types).
- `sketch.html` template with the two-column layout (DAG tree + Tweakpane folders).
- DAG rendered as an HTML/CSS hierarchical tree. Each node is an `<a>` that opens the step view in a new tab.
- Tweakpane now shows folders (one per step), populated from the full params endpoint.

**What stays thin:**

- DAG layout is a simple vertical tree. No fancy positioning.

### Acceptance test (pytest)

```python
def test_dag_endpoint_reflects_pipeline_structure(tmp_sketch, test_client):
    """The DAG endpoint returns the correct graph for a multi-step pipeline."""
    dag = test_client.get("/api/sketches/edge_portrait/dag").json()

    node_ids = {n["id"] for n in dag["nodes"]}
    assert "source_photo" in node_ids
    assert "gaussian_blur_0" in node_ids
    assert "edge_detect_0" in node_ids

    # Edges reflect the chain
    edges = {(e["from"], e["to"]) for e in dag["edges"]}
    assert ("source_photo", "gaussian_blur_0") in edges
    assert ("gaussian_blur_0", "edge_detect_0") in edges

def test_sketch_page_renders_all_steps(tmp_sketch, test_client):
    """The sketch overview page contains links to all step views."""
    response = test_client.get("/sketch/edge_portrait")
    assert response.status_code == 200
    assert "gaussian_blur_0" in response.text
    assert "edge_detect_0" in response.text

def test_all_step_params_in_sketch_view(tmp_sketch, test_client):
    """The full params endpoint returns params for all steps."""
    params = test_client.get("/api/sketches/edge_portrait/params").json()
    assert "gaussian_blur_0" in params
    assert "edge_detect_0" in params
```

### Definition of done — Increment 4

- [ ] Acceptance tests in `tests/acceptance/test_04_dag_overview.py` pass
- [ ] `tests/unit/test_dag.py` updated: topo sort over 3+ node chain, correct order guaranteed
- [ ] `tests/unit/test_sketch.py` updated: `Sketch.add()` with explicit inputs wires correctly into DAG
- [ ] `tests/unit/test_gaussian_blur.py` covers `GaussianBlur.setup` declares correct params, `process` returns same-shape image

---

## Increment 5: Explicit Wiring and Optional Inputs

### Acceptance test

> I define a sketch where edge detection takes an explicit mask input from a second source node. The mask is optional — the sketch works without it. I add the mask source, wire it in with `self.add(..., inputs={...})`, and the edge detection uses it. I edit the mask file on disk, and only the downstream steps re-execute.

### What this drives

**Core engine additions:**

- Optional inputs on steps — `add_input(..., optional=True)`.
- `Sketch.add()` with explicit `inputs={}` dict — the full wiring API.
- `DAG.descendants(node)` — given a changed node, compute what needs re-executing.
- Executor partial re-execution: only run descendants of changed nodes.
- File watcher watches multiple source files per sketch.

**Server additions:**

- DAG visualization now shows branching/merging (mask feeds into edge detect alongside blur output).

### Acceptance test (pytest)

```python
async def test_mask_change_only_reruns_downstream(tmp_sketch, test_client, ws_client):
    """Changing the mask file re-executes edge_detect but not blur."""
    async with ws_client("/ws/edge_portrait") as ws:
        write_test_image(tmp_sketch / "assets" / "mask.png", color="white")

        # Collect all step_updated messages within a short window
        updated_steps = set()
        try:
            while True:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
                if msg["type"] == "step_updated":
                    updated_steps.add(msg["step_id"])
        except asyncio.TimeoutError:
            pass

        assert "edge_detect_0" in updated_steps
        assert "gaussian_blur_0" not in updated_steps

def test_optional_input_not_required(tmp_sketch_no_mask, test_client):
    """A sketch with an optional mask input works when no mask is wired."""
    response = test_client.get("/sketch/edge_portrait_no_mask/step/edge_detect_0")
    assert response.status_code == 200
```

### Definition of done — Increment 5

- [ ] Acceptance tests in `tests/acceptance/test_05_explicit_wiring.py` pass
- [ ] `tests/unit/test_dag.py` updated: `descendants()` returns correct subgraph, partial re-execution skips non-descendants
- [ ] `tests/unit/test_step.py` updated: optional input not required at execution time, missing required input raises at DAG validation
- [ ] `tests/unit/test_sketch.py` updated: `add()` with `inputs={}` dict wires named inputs correctly

---

## Increment 6: Sketch Browser and Multi-Sketch Discovery

### Acceptance test

> I have two sketch modules under `sketchbook.sketches`. I run `uv run dev` and open the browser root. I see a list of both sketches with their names and descriptions. I click one and land on its sketch overview page. The other sketch's watchers are not running.

### What this drives

**Core engine additions:**

- Sketch discovery — scan `sketchbook.sketches` submodules for `Sketch` subclasses, import them, register them.
- Lazy activation — watchers start only for the active sketch, tear down on navigate-away.

**Server additions:**

- `GET /` — index page listing all sketches.
- `index.html` template — list of sketch cards with name, description, date.
- Activation/deactivation lifecycle tied to WebSocket connections (last WS disconnects → deactivate).

### Acceptance test (pytest)

```python
def test_index_lists_all_sketches(two_sketches, test_client):
    """The index page lists all discovered sketches."""
    response = test_client.get("/")
    assert "Edge Portrait" in response.text
    assert "Hello" in response.text

def test_only_active_sketch_watches_files(two_sketches, test_client, watcher_registry):
    """Only the sketch being viewed has active file watchers."""
    # Navigate to edge_portrait
    test_client.get("/sketch/edge_portrait")
    assert watcher_registry.is_active("edge_portrait")
    assert not watcher_registry.is_active("hello")
```

### Definition of done — Increment 6

- [ ] Acceptance tests in `tests/acceptance/test_06_sketch_browser.py` pass
- [ ] `tests/unit/test_discovery.py` covers sketch discovery (finds all `Sketch` subclasses in `sketchbook.sketches.*`, skips non-sketch modules)
- [ ] `tests/unit/test_watcher.py` covers lazy activation (watcher starts on activate, stops on deactivate, does not start for inactive sketches)

---

## Increment 7: Static Site Generation

### Acceptance test

> I define a sketch with a `site_output()` node and two saved presets. I run `uv run build`. A `dist/` folder appears with an `index.html` feed page linking to the sketch, and a sketch page showing both variants with their baked images. The images are real rendered output, not symlinks.

### What this drives

**Core engine additions:**

- `SiteOutput` step — marks a node for inclusion in the static site build.
- `Sketch.site_output()` DSL method.

**Site builder:**

- `site/builder.py` — discovers sketches, finds `SiteOutput` nodes, iterates saved presets, executes pipeline for each, copies output images to `dist/`.
- `site/templates/feed.html` — renders the feed page.
- `site/templates/sketch_page.html` — renders individual sketch pages with variant gallery.

**CLI:**

- `uv run build` invokes the site builder.

### Acceptance test (pytest)

```python
def test_build_produces_site_with_variants(tmp_project_with_presets):
    """uv run build generates a static site with feed and variant images."""
    result = subprocess.run(["uv", "run", "build"], capture_output=True, cwd=tmp_project_with_presets)
    assert result.returncode == 0

    dist = tmp_project_with_presets / "dist"
    assert (dist / "index.html").exists()
    assert (dist / "edge-portrait" / "index.html").exists()

    # Both presets should produce variant images
    assert (dist / "edge-portrait" / "variants" / "heavy_edges.png").exists()
    assert (dist / "edge-portrait" / "variants" / "soft_edges.png").exists()

    # Feed page links to the sketch
    feed_html = (dist / "index.html").read_text()
    assert "edge-portrait" in feed_html

    # Variant images are real image files, not empty
    img_bytes = (dist / "edge-portrait" / "variants" / "heavy_edges.png").read_bytes()
    assert len(img_bytes) > 100

def test_build_without_site_output_produces_empty_feed(tmp_project_no_site_output):
    """A sketch with no site_output node doesn't appear in the build."""
    result = subprocess.run(["uv", "run", "build"], capture_output=True, cwd=tmp_project_no_site_output)
    assert result.returncode == 0

    feed_html = (tmp_project_no_site_output / "dist" / "index.html").read_text()
    assert "hello" not in feed_html
```

### Definition of done — Increment 7

- [ ] Acceptance tests in `tests/acceptance/test_07_static_site.py` pass
- [ ] `tests/unit/test_builder.py` covers: discovers `SiteOutput` nodes, iterates presets, renders feed and sketch pages, copies baked images to `dist/`, sketch with no `SiteOutput` is absent from feed

---

## Increment 8: Deploy to GitHub Pages

### Acceptance test

> I run `uv run deploy`. It builds the site and pushes `dist/` to the `gh-pages` branch. The main branch is not affected.

### What this drives

**CLI:**

- `uv run deploy` — runs build, then force-pushes `dist/` to `gh-pages` branch.
- Uses `ghp-import` or `git subtree split` + push.

### Acceptance test (pytest)

```python
def test_deploy_pushes_to_gh_pages(tmp_project_with_git):
    """Deploy creates/updates the gh-pages branch with built content."""
    result = subprocess.run(["uv", "run", "deploy"], capture_output=True, cwd=tmp_project_with_git)
    assert result.returncode == 0

    # gh-pages branch should exist and contain index.html
    result = subprocess.run(
        ["git", "show", "gh-pages:index.html"],
        capture_output=True, cwd=tmp_project_with_git
    )
    assert result.returncode == 0
    assert b"<html" in result.stdout
```

### Definition of done — Increment 8

- [ ] Acceptance tests in `tests/acceptance/test_08_deploy.py` pass
- [ ] `tests/unit/test_deploy.py` covers: build runs before push, `gh-pages` branch updated, `main` branch unaffected

---

## Reference: Key Abstractions

These are the core types that get built up incrementally across the above. Documented here for reference — not as a separate build phase.

### PipelineStep

```python
class PipelineStep:
    """Base class for all pipeline steps."""

    def setup(self):
        """Declare inputs and parameters. Called once at build time."""
        raise NotImplementedError

    def process(self, inputs: dict, params: dict) -> Any:
        """Execute the step. Called every time inputs or params change."""
        raise NotImplementedError

    # Framework-provided methods available in setup():
    def add_input(self, name: str, type: type, optional: bool = False): ...
    def add_param(self, name: str, type: type, default: Any, **constraints): ...
    # constraints: min, max, step, choices (for enums/dropdowns)
```

### Sketch DSL

```python
class Sketch:
    name: str
    description: str
    date: str

    def build(self):
        """Override to define the pipeline."""
        raise NotImplementedError

    def source(self, name: str, path: str) -> DAGNode: ...
    def add(self, step_class: type, inputs: dict, id: str = None) -> DAGNode: ...
    def output(self, node: DAGNode, path: str) -> DAGNode: ...
    def site_output(self, node: DAGNode, **metadata) -> DAGNode: ...

class DAGNode:
    def pipe(self, step_class: type, input_name: str = "image", **extra_inputs) -> DAGNode: ...
```

### DAG

- `DAGNode`: wraps a step instance, holds edges, stores cached output and `.workdir` path.
- `DAG`: `add_node()`, `connect()`, `topo_sort()`, `descendants(node)`, `validate()`.

### Param / Preset JSON Format

```json
{
  "_meta": {
    "based_on": "heavy_edges",
    "dirty": true
  },
  "edge_detect_0": {
    "threshold1": 120.0,
    "threshold2": 200.0
  },
  "gaussian_blur_0": {
    "kernel_size": 5
  }
}
```

Tweakpane schema mapping: `float`/`int` with min/max/step → slider, `bool` → checkbox, `str` → text input, `enum` → dropdown, `float` with `color=True` → color picker.

### Server Routes

**Pages:**

- `GET /` — sketch browser
- `GET /sketch/{sketch_id}` — sketch overview (DAG + Tweakpane for all steps)
- `GET /sketch/{sketch_id}/step/{step_id}` — fullscreen step view (image + Tweakpane for that step)

**API:**

- `GET /api/sketches/{sketch_id}/params` — all steps' param schema + values
- `GET /api/sketches/{sketch_id}/params/{step_id}` — single step's param schema + values
- `PATCH /api/sketches/{sketch_id}/params` — update a param value
- `GET /api/sketches/{sketch_id}/presets` — list presets + active state
- `POST /api/sketches/{sketch_id}/presets` — save named preset
- `POST /api/sketches/{sketch_id}/presets/{name}/load` — load preset
- `GET /api/sketches/{sketch_id}/dag` — DAG structure as JSON

**WebSocket:**

- `WS /ws/{sketch_id}` → `step_updated`, `params_changed`, `preset_state`

### Frontend Layout

Sketch overview:

```
┌─────────────────────────────────────────────┐
│  Sketch: Edge Portrait          [presets ▼]  │
├──────────────────────┬──────────────────────┤
│                      │                      │
│   DAG Overview       │   Tweakpane Panel    │
│   (HTML/CSS tree)    │   (per-step folders) │
│                      │                      │
│   [source: photo] ↗  │   ┌ EdgeDetect ─────┐│
│        │             │   │ threshold1 ▓░░ ││
│   [EdgeDetect] ↗     │   │ threshold2 ▓▓░ ││
│        │             │   └─────────────────┘│
│   [output: file] ↗   │                      │
│                      │                      │
└──────────────────────┴──────────────────────┘
```

Step fullscreen:

```
┌──────────────────────────────────────────────┐
│  EdgeDetect  (Edge Portrait)     [presets ▼]  │
├──────────────────────────────┬───────────────┤
│                              │  Tweakpane    │
│     Step Output Image        │  (this step   │
│     (live-updating)          │   only)       │
│                              │               │
└──────────────────────────────┴───────────────┘
```

---

## Dependencies

```toml
[project]
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "jinja2",
    "watchdog",
    "opencv-python-headless",
    "numpy",
    "websockets",
]

[project.scripts]
# Defined as uv scripts
```

---

## Open Questions / Future Work

- **Hot-reload of sketch Python code**: Currently, changing a sketch's `__init__.py` requires restarting the dev server. Could add importlib reload, but it's tricky. Defer.
- **Non-image types**: The architecture supports it (types.py is generic), but the UI and Tweakpane integration assume images for now.
- **Sketch-level presets**: Layer on top of per-step presets later. Just snapshot which step presets are loaded.
- **Smart caching**: Hash-based skip for unchanged steps. Add when build times become a problem.
- **Custom site templates per sketch**: Allow a sketch module to include its own Jinja2 template.
- **Video / animation output**: Executing a sketch across a range of param values to produce frames.
- **Parallel execution**: Independent branches of the DAG could run concurrently. Not needed until pipelines get complex.
