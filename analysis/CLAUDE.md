# CLAUDE.md

Python project for analyzing images and producing structured data for sketches to consume. Runs locally only; artifacts are checked into version control.

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
