# CLAUDE.md

Python project for analyzing images and producing structured data for sketches to consume. Runs locally only; artifacts are checked into version control.

## Principles

- **Analysis is purely code, not state.** No persistent data lives here. The `analysis/` directory contains only code and dependencies.
- **Sketches own their assets.** A sketch's images and other assets are the source of truth and live under that sketch's `assets/` directory (e.g. `site/sketches/<name>/assets/`). Analysis reads from and writes to those locations directly.
- **No staging directories in the repo.** If a temporary working directory is needed during analysis, use `/tmp`. Never create a staging or scratch directory inside `analysis/`.

## Tooling

- Managed by [uv](https://docs.astral.sh/uv/)
- Python version pinned via `pyproject.toml` (`requires-python`)
- Virtual environment at `.venv/` (created and managed by uv)
- mise auto-sources the uv venv when inside this directory

## Commands

```bash
uv run main.py          # run the main script
uv add <package>        # add a dependency
uv sync                 # install/sync dependencies
```
