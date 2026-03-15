# analysis

Python tooling for analyzing sketch assets and producing structured data for sketches to consume. Runs locally only; pipeline outputs are written back to sketch asset directories and committed there.

## Quick start

```bash
uv sync
```

## Running a pipeline

```bash
uv run analysis run <pipeline> <sketch>
uv run analysis run <pipeline> <sketch> --image <stem>
```

Examples:

```bash
uv run analysis run edges tree-bark-tile          # all images in sketch
uv run analysis run edges tree-bark-tile --image tile  # one image by stem
uv run analysis list-sketches
uv run analysis list-pipelines
```

Outputs are written to `site/sketches/<sketch>/assets/<stem>.<pipeline>.json`. Commit the outputs alongside the sketch.

## Playground experiments

Write one-off scripts in `playground/`. Scripts are committed as reference but are not productionized pipelines. Use the shared utilities to resolve sketch paths:

```python
from sketchbook.paths import sketch_assets_dir, sketch_image_paths, find_image
```

Run with `uv run python playground/my_experiment.py`. Write output to `/tmp`.

## Adding a pipeline

1. Create `pipelines/<name>/` with `__init__.py`, `pipeline.py`, and `README.md`
2. Implement `run(sketch_name, image_stem=None)` in `pipeline.py`
3. Document the output JSON schema as a TypeScript interface in `README.md`
4. The CLI auto-discovers the pipeline — no registration needed

See `pipelines/README.md` for full conventions.

## Tooling

Managed by [uv](https://docs.astral.sh/uv/). Python version pinned in `pyproject.toml`. mise auto-activates the uv virtualenv when inside this directory.

## Principles

- **Purely code, not state.** No persistent data lives here. Only code and dependencies.
- **Sketches own their assets.** Images and other files are the source of truth at `site/sketches/<name>/assets/`. Analysis reads from and writes to those locations directly.
- **No staging directories in the repo.** Use `/tmp` for any temporary working directories.
- **Playground is for reference, not production.** Scripts in `playground/` are committed as exploration history. Never write pipeline outputs from playground scripts to `site/sketches/`.
