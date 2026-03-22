# site

Static site for [mattpace.art](https://mattpace.art), built with [Eleventy](https://www.11ty.dev/).

## How it works

The site reads a `bundle/` directory containing a `manifest.json` and baked images produced by `uv run build` (the Sketchbook build system). Eleventy uses the manifest as data to generate:

- An **index page** listing all sketches
- A **detail page** per sketch showing its variants (one per preset)

The `bundle/` directory is a symlink to `sketches/bundle/` created by the sketch build step. It is not checked in.

## Development

```sh
npm run dev     # start 11ty dev server
npm run build   # generate static site to dist/
```

Or via mise from the repo root:

```sh
mise run site:dev
mise run site:build
```

## Deployment

`mise run deploy` from the repo root builds everything (sketch bundles + site) then force-pushes `site/dist/` to the `gh-pages` branch via `scripts/deploy.sh`.

## Structure

```
site/
├── index.html          # home page (lists all sketches)
├── sketch.html         # sketch detail (paginated from manifest)
├── _data/
│   └── manifest.js     # reads bundle/manifest.json as 11ty data
├── assets/             # CC license icons
├── scripts/
│   └── deploy.sh       # gh-pages push script
├── CNAME               # GitHub Pages custom domain
├── favicon.png
└── dist/               # built output (gitignored)
```
