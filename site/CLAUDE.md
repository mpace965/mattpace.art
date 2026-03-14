# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this directory.

## Commands

```bash
npm run dev     # dev server (default port 8080)
npm run build   # build to _site/
```

No linter, no test suite.

## Principles

- **No-build for sketches.** Sketches are plain HTML/JS. No bundler, no transpiler. Vendor deps are checked in under `vendor/` and imported via relative ES module paths.
- **Each sketch is self-contained.** No shared sketch code. Code reuse through copy/paste is intentional and preferred. Don't introduce dependencies between sketches.
- **One idea per sketch.** When something new occurs, open a new file rather than adding to an existing one.
- **Save versions.** Either duplicate the file or use git. Iterate in new sketches, not over good ones.
- **11ty is for the shell only.** Eleventy handles the index/feed page and static site generation. Sketches themselves are just files.

## Architecture

11ty static site. Sketch `index.html` files are processed by Eleventy (for frontmatter/collection), but their JS, assets, and `jsconfig.json` are passthrough-copied unchanged. The default template language for `.html` files is Liquid — use Liquid syntax in all templates.

**Vendor deps:** `p5@1.11.11`, `tweakpane@4.0.5`, `@vue/reactivity@3.5.23`

**Each sketch** lives in `sketches/<name>/` with `index.html` + `index.js`. Copy `sketches/_template/` to start a new one.

### Sketch index.html frontmatter

Sketch HTML files use YAML frontmatter for feed metadata. Eleventy strips it and outputs the HTML unchanged:

```yaml
---
title: My Sketch
date: 2024-01-15
description: One sentence about what it does.
presets:
  - preset-name
---
```

The optional `presets` list renders `?preset=<name>` links in the feed, one per entry. Include a preset name here for each named preset defined in `PRESETS` in `index.js`.

### Sketch conventions (index.js)

- Imports at top via relative ES module paths (`../../vendor/...`)
- Params typed via JSDoc `@typedef Params`, stored as a `PRESETS` record
- `mountSketch(params)` sets `globalThis.setup` and `globalThis.draw` for p5
- `mountTweakpane(title)` wires Tweakpane UI to params
- Preset selection via URL search param `?preset=<name>`; `h` key hides/shows the pane
- `@vue/reactivity` `ref()` used in the template to make params reactive
