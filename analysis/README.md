# analysis

Python tooling for analyzing sketch assets and producing structured data for sketches to consume. Runs locally only; artifacts are checked into version control alongside the sketches that use them.

## Commands

```bash
uv run main.py      # run the main script
uv add <package>    # add a dependency
uv sync             # install/sync dependencies
```

## Principles

- **Purely code, not state.** No persistent data lives here. Only code and dependencies.
- **Sketches own their assets.** Images and other files are the source of truth and live under `site/sketches/<name>/assets/`. Analysis reads from and writes to those locations directly.
- **No staging directories in the repo.** Use `/tmp` for any temporary working directories.

## Tooling

Managed by [uv](https://docs.astral.sh/uv/). Python version pinned in `pyproject.toml`. mise auto-activates the uv virtualenv when inside this directory.
