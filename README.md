# mattpace.art

A creative sketchbook — generative art sketches built with p5.js, published as a static site.

## Structure

```
site/        11ty static site (the sketchbook)
analysis/    Python tooling for image analysis; artifacts checked into version control
```

## Tooling

Versions are managed with [mise](https://mise.jdx.dev/). Run `mise install` at the repo root to get the right Node and Python versions.

## Development

```bash
cd site
npm install
npm run dev      # dev server at http://localhost:8080
```

To create a new sketch:

```bash
npm run new      # scaffolds a new sketch from the template
```

## Deployment

The site deploys to GitHub Pages on push to `main` via GitHub Actions. The `analysis/` directory is not part of CI.
