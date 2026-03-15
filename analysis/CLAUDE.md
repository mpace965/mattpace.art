# CLAUDE.md

Python project for analyzing images and producing structured data for sketches to consume. Runs locally only; pipeline artifacts are checked into version control alongside the sketches that use them.

## Principles

- **Analysis is purely code, not state.** No persistent data lives here. Only code and dependencies.
- **Sketches own their assets.** A sketch's images and other files are the source of truth at `site/sketches/<name>/assets/`. Analysis reads from and writes to those locations directly.
- **No staging directories in the repo.** Use `/tmp` for temporary work. Never create scratch directories inside `analysis/`.
- **Playground is for reference, not production.** Scripts in `playground/` are committed as exploration history but are not productionized pipelines. Never write pipeline outputs from playground scripts to `site/sketches/`.

## Tooling

- Managed by [uv](https://docs.astral.sh/uv/)
- Python version pinned via `pyproject.toml`
- Virtual environment at `.venv/` (created and managed by uv)
- mise auto-sources the uv venv when inside this directory

## Commands

```bash
uv run analysis run <pipeline> <sketch>                # run a pipeline against all sketch images
uv run analysis run <pipeline> <sketch> --image <stem> # run against one image by stem
uv run analysis list-sketches                          # list available sketches
uv run analysis list-pipelines                         # list available pipelines
uv run python playground/my_experiment.py              # run a playground script
uv add <package>                                       # add a dependency
uv sync                                                # install/sync dependencies
```

## Structure

- `sketchbook/paths.py` — shared utility for resolving sketch paths. All pipeline and playground code imports from here. Never hardcode repo-relative paths.
- `pipelines/<name>/pipeline.py` — each pipeline exposes `run(sketch_name, image_stem=None)`.
- `pipelines/<name>/README.md` — pipeline contract: input spec, output spec, JSON schema as TypeScript interface.
- `pipelines/README.md` — conventions and registry of available pipelines.
- `playground/` — committed experiment scripts for exploration and reference. Not productionized pipelines.
- `main.py` — CLI dispatcher. Uses argparse subcommands; auto-discovers pipelines by scanning `pipelines/*/pipeline.py`.

## Output naming convention

Pipeline outputs follow `<image-stem>.<pipeline-name>.json` and are written to `site/sketches/<name>/assets/`. All output JSON must include a top-level `version` integer field. Increment it when the schema changes incompatibly.

## Adding a pipeline

Create `pipelines/<name>/` with:
- `__init__.py` (empty)
- `pipeline.py` with `def run(sketch_name: str, image_stem: str | None = None) -> None`
- `README.md` documenting the TypeScript interface for the output JSON

The CLI dispatcher auto-discovers new pipelines — no registration needed. Update `pipelines/README.md` to add the pipeline to the registry.

## Sketch path resolution

Always use `sketchbook.paths` — never hardcode paths. Key functions:
- `sketch_assets_dir(sketch_name)` — returns `Path` to `site/sketches/<name>/assets/`
- `sketch_image_paths(sketch_name)` — returns all image `Path`s in assets/
- `find_image(sketch_name, stem)` — finds a single image by stem (no extension needed)
- `list_sketches()` — returns all sketch names
