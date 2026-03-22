# Sketchbook

A reactive, DAG-based pipeline framework for creative coding. Designed for an agentic workflow where you write pipeline steps in Python — by hand or with an AI coding agent — and the framework handles execution, live preview, and static output generation.

## Philosophy

Sketchbook provides the **infrastructure** for running pipelines, not the pipeline steps themselves. The framework knows how to:

- Build and validate a DAG of processing steps
- Execute the DAG in topological order, with partial re-execution on change
- Watch source files and propagate changes in real time
- Serve a dev UI for inspecting every intermediate step and tuning parameters via Tweakpane
- Persist parameter presets as JSON files
- Build static output bundles (baked images + JSON manifest) for downstream publishing

It does **not** know how to blur an image, detect edges, or do any domain-specific transformation. Those are userland concerns — steps written by the sketch author. This makes the framework publishable as an independent package with no opinion on what kind of data flows through the pipeline.

> There is currently an OpenCV dependency for `Image` load/save. This will eventually be replaced to make the framework fully domain-agnostic.

## Core concepts

### PipelineStep

Base class for all pipeline steps. Subclass it to define a transform:

```python
from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image

class GaussianBlur(PipelineStep):
    """Apply a Gaussian blur."""

    def setup(self):
        self.add_input("image", Image)
        self.add_param("sigma", float, default=1.0, min=0.1, max=10.0, step=0.1)

    def process(self, inputs: dict, params: dict) -> Image:
        # your implementation here
        ...
```

- `setup()` declares inputs and parameters (called once at build time)
- `process(inputs, params)` executes the step (called when inputs or params change)
- Parameters get Tweakpane controls automatically in the dev UI

### Sketch

Base class for a pipeline definition. A sketch wires steps together:

```python
from sketchbook import Sketch

class MySketch(Sketch):
    name = "my sketch"
    description = "a simple pipeline"
    date = "2026-03-20"

    def build(self):
        photo = self.source("photo", "assets/input.jpg")
        result = photo.pipe(GaussianBlur)
```

DSL methods:
- `source(name, path)` — add a file source node
- `node.pipe(StepClass)` — chain a step (fluent API)
- `add(StepClass, inputs={...})` — explicit multi-input wiring
- `output_bundle(node, bundle_name)` — mark a node for static build output

### DAG

The directed acyclic graph is the source of truth. The executor walks it in topological order. The server renders it. The file watcher knows what to watch because of it. `DAG.descendants()` enables partial re-execution — only downstream nodes re-run when an upstream input changes.

### Presets

Parameter values live in JSON files under each sketch's `presets/` directory. `_active.json` holds the current working state. Named presets can be saved, loaded, and swapped via the dev UI or API. Dirty tracking shows when the active state has diverged from a saved preset.

## Dev server

The dev server (`uv run dev`) starts a FastAPI app that:

- Discovers sketch modules by scanning for `Sketch` subclasses
- Builds each sketch's DAG and executes it
- Watches source files with `watchdog` and re-executes affected subgraphs
- Pushes `step_updated` events over WebSocket for live browser refresh
- Serves a sketch browser, DAG overview, and per-step fullscreen views
- Renders Tweakpane controls from parameter definitions

### Routes

| Route | Description |
|---|---|
| `GET /` | Sketch browser |
| `GET /sketch/{id}` | Sketch overview (DAG + params) |
| `GET /sketch/{id}/step/{step_id}` | Fullscreen step view |
| `GET /api/sketches/{id}/dag` | DAG structure as JSON |
| `GET /api/sketches/{id}/params` | All params (schema + values) |
| `PATCH /api/sketches/{id}/params` | Update a parameter |
| `GET /api/sketches/{id}/presets` | List presets |
| `POST /api/sketches/{id}/presets` | Save preset |
| `POST /api/sketches/{id}/presets/{name}/load` | Load preset |
| `WS /ws/{id}` | Live update stream |

## Build system

`uv run build` scans sketches for `OutputBundle` nodes, iterates their `presets` list (or all saved presets if `presets=None`), executes the full pipeline for each preset, and writes baked images + a `manifest.json` to the output directory. This manifest is consumed by downstream tooling (e.g., an 11ty static site).

## Package structure

```
src/sketchbook/
├── __init__.py
├── cli.py              # dev and build entry points
├── discovery.py        # sketch module scanner
├── core/
│   ├── dag.py          # DAG graph, topo sort, descendants
│   ├── step.py         # PipelineStep base class
│   ├── sketch.py       # Sketch base class and build DSL
│   ├── types.py        # Image type (numpy wrapper)
│   ├── params.py       # ParamDef, ParamRegistry
│   ├── presets.py      # PresetManager (JSON file I/O)
│   ├── executor.py     # DAG execution engine
│   └── watcher.py      # File watching with watchdog
├── server/             # FastAPI app, routes, templates, static
├── steps/              # Framework-provided steps (SourceFile, OutputBundle)
└── site/
    └── builder.py      # Static bundle builder
```

## Dependencies

```
fastapi, uvicorn, jinja2, watchdog, websockets  # server
numpy, opencv-python-headless                    # image I/O (to be decoupled)
```

## Testing

```sh
uv run --directory framework pytest
```

Tests follow the GOOS double-loop: acceptance tests in `tests/acceptance/` drive end-to-end behavior, unit tests in `tests/unit/` drive individual object design. Test steps are defined in `tests/steps.py` — the framework test suite never imports from userland sketches.
