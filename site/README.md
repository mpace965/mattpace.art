# site

11ty static site for the sketchbook. Each sketch is a self-contained HTML/JS experiment.

## Commands

```bash
npm install
npm run dev      # dev server at http://localhost:8080
npm run build    # build to _site/
npm run new      # scaffold a new sketch from the template
```

## Structure

```
sketches/           one directory per sketch
  _template/        copy this to start a new sketch
  <name>/
    index.html      frontmatter + HTML; processed by Eleventy
    index.js        sketch logic (plain ES modules, no bundler)
    assets/         sketch-specific assets (images, data, etc.)
vendor/             checked-in JS dependencies (p5, tweakpane, @vue/reactivity)
assets/             site-level assets
```

## Principles

- Sketches are plain HTML/JS — no bundler, no transpiler.
- Each sketch is self-contained. No shared sketch code; copy/paste is intentional.
- One idea per sketch. Start a new file rather than modifying an existing one.
- Sketches own their assets. Images and data live under the sketch's `assets/` directory.
- 11ty is for the shell only (index/feed page). Sketch files are passed through unchanged.
