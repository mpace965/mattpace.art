# CLAUDE.md

## What is this project?

Sketchbook is a reactive, DAG-based creative coding environment for image processing pipelines. Sketches are Python classes that wire together pipeline steps (transformations on images). In dev mode, a FastAPI server watches source files and propagates changes through the pipeline in real time, with every intermediate step inspectable in the browser.

The full implementation plan is in `sketchbook-implementation-plan.md`.

## Python standards

This is a modern Python project. Target Python 3.14.

- **`mise`** for runtime version management. Python version is pinned in `.mise.toml`. No pyenv, no asdf.
- **Type hints everywhere.** Every function signature, every return type, every class attribute. Use `str | None` not `Optional[str]`. Use `list[str]` not `List[str]`. Use `Self` from `typing` where appropriate.
- **Dataclasses and plain classes over pydantic** for internal domain models. Pydantic is fine at the API boundary (FastAPI request/response models) but the core pipeline engine should have no pydantic dependency.
- **f-strings** for all string formatting. Never `.format()`, never `%`.
- **pathlib.Path** for all filesystem operations. Never `os.path`. Accept `str | Path` at public API boundaries, convert to `Path` immediately.
- **`uv`** for package management. No pip, no poetry, no conda.
- **`uv run`** for all Python execution. Never use bare `python`, `python3`, or `mise exec -- python`. Examples: `uv run python`, `uv run pytest`.
- **Ruff** for linting and formatting. No black, no isort, no flake8.
- **Strict imports.** No wildcard imports. No `from module import *`.
- **Docstrings** on every public class and every public method. One-liner is fine if the intent is obvious. Use imperative mood ("Return the image" not "Returns the image").
- **No classes where a function will do.** But pipeline steps are classes — that's a deliberate design choice for lifecycle and introspection, not Java brain.

## Userland vs framework

**Framework** is everything under `framework/`. It is the engine, server, site builder, CLI, and test infrastructure. It knows nothing about any specific sketch.

**Userland** is everything under `sketches/`. Each sketch directory is a self-contained creative module. Sketches depend on the framework. The framework never depends on sketches.

### Steps belong to sketches

The framework provides the `PipelineStep` base class and the infrastructure to run steps (DAG, executor, server, watcher). It does **not** provide reusable processing steps. Steps like `GaussianBlur` or `EdgeDetect` live in the sketch that first needs them. If a step proves useful across many sketches it may be promoted to the framework — but conservatively, and only once the pattern is clearly general.

### The hard rule: framework never imports from sketches

`framework/src/sketchbook/` must never import from `sketches.*`. `framework/tests/` must never import from `sketches.*`. Tests that need concrete steps define them in `framework/tests/steps.py` or inline. Violating this collapses the dependency boundary and makes sketches load-order dependencies of the framework itself.

## Architecture principles

### The DAG is the source of truth

Everything flows from the DAG. The executor walks it. The server renders it. The file watcher knows what to watch because of it. The static site builder scans it. If something isn't in the DAG, it doesn't exist.

### Sketches are self-contained modules

Each sketch lives in its own directory under `sketches/` (at the repo root) with its own `assets/`, `presets/`, and `.workdir/`. A sketch should be deletable by removing its folder. No central registry file — discovery is by convention (scan for `Sketch` subclasses in `sketches.*`).

### Intermediates are cheap and disposable

Everything under `.workdir/` is ephemeral. It can be deleted at any time and will be regenerated on the next run. Never store anything meaningful there. Never reference `.workdir/` paths in user-facing config.

### Nothing writes to the workspace unless explicitly wired

The pipeline engine writes intermediates to `.workdir/` and that's it. The only way to write to the main workspace is through an output node (`FileOutput`, `SiteOutput`). This is a safety invariant — a sketch should never be able to corrupt its own source assets.

### Parameters are data, not code

All parameter values live in JSON files. The Python code declares the schema (type, default, constraints), the JSON files hold the state. This separation means params can be edited in the browser, diffed in git, and swapped via presets without touching Python.

### The browser is for viewing and tuning, not authoring

The dev server UI is for inspecting pipeline outputs and tweaking parameters. You author sketches in your editor. You edit masks in your image editor. The browser shows you the results. Don't try to build an IDE in the browser.

## Code style

### Keep functions short and obvious

If a function needs a block comment explaining what the next 20 lines do, extract those 20 lines into a function whose name is that comment.

### Errors should be loud and clear

Raise specific exceptions with messages that tell the user what went wrong and what to do about it. `raise ValueError(f"Step '{step_id}' has no input named 'mask'. Available inputs: {list(step.inputs)}")` is good. `raise ValueError("invalid input")` is not.

### No silent defaults for required things

If a step requires an input, it must be connected. Don't silently substitute a black image or a zero array. Fail at DAG validation time, not at process time.

### Logging, not print

Use `logging` with the `sketchbook` logger hierarchy. `print()` is for CLI output only (e.g., build progress). Debug-level logs for "executing step X", info-level for "watching file Y", warning for "preset file missing, using defaults".

### Tests

Use `pytest`. Test the core engine (DAG construction, topo sort, execution, param serialization) thoroughly. Server tests can use FastAPI's `TestClient`. Don't test Tweakpane or browser JS — that's manual for now.

## Increment workflow (GOOS double-loop)

Every increment follows this order. Do not skip steps.

1. **Write the acceptance test first.** It will fail. That's correct. The acceptance test lives in `tests/acceptance/` and defines the end-to-end behaviour for the increment.
2. **Pick the first failing unit.** What's the simplest class or function the acceptance test needs? Write a unit test for it in `tests/unit/` — just enough to fail.
3. **Make the unit test pass.** Write the minimum implementation.
4. **Repeat the inner loop** (unit test → implementation) for each collaborator until the acceptance test goes green.
5. **Refactor.** Both loops are green — now clean up.

**Hard rules:**

- If you are writing implementation code without a failing unit test, stop. Write the unit test first.
- Every new class or non-trivial function introduced in an increment gets a unit test. No exceptions.
- The acceptance test is not a substitute for unit tests. It tells you the system works end-to-end; unit tests tell you which part broke and drive the design of individual objects.
- Each increment in `sketchbook-implementation-plan.md` has a "Definition of done" checklist. All boxes must be checked before the increment is complete.

## Dependencies

Be conservative. Every dependency is a liability. The core engine should only need `numpy` and `opencv-python-headless`. The server adds `fastapi`, `uvicorn`, `jinja2`, `watchdog`, `websockets`. That's it. Think hard before adding anything else.

If you need a utility function that exists in a library, consider whether it's shorter to just write it. If the answer is yes, write it.

## File conventions

- Sketch modules: `sketches/<slug>/__init__.py`
- Sketch assets: `sketches/<slug>/assets/`
- Presets: `sketches/<slug>/presets/*.json`
- Active params: `sketches/<slug>/presets/_active.json`
- Intermediates: `sketches/<slug>/.workdir/` (gitignored)
- Built site: `dist/` (gitignored)

## Git

- **`mise run lint` must pass before every commit.** No exceptions. Fix all violations first.
- `.workdir/` directories are always gitignored.
- `dist/` is gitignored on main. It gets force-pushed to `gh-pages` for deployment.
- Source assets under `sketches/*/assets/` are **not** committed (too large). The repo works without them — you just can't build until you have the assets locally.
- Presets **are** committed. They're small JSON files and they represent creative decisions worth versioning.
