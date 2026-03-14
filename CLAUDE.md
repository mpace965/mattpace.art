# CLAUDE.md

This is a monorepo with two top-level directories:

- **`site/`** — 11ty static site (the sketchbook). See `site/CLAUDE.md`.
- **`analysis/`** — Python project for analyzing images and producing structured data for sketches to consume. See `analysis/CLAUDE.md`. Runs locally only; artifacts are checked into version control.

## Tooling

Versions are managed with [mise](https://mise.jdx.dev/) via `.mise.toml` at the repo root.

## Deployment

The site deploys to GitHub Pages on push to `main` via `.github/workflows/deploy.yml`. The `analysis/` directory is not part of CI.
