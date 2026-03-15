# pipelines

Productionized image processing pipelines. Each pipeline reads from a sketch's `assets/` directory and writes structured JSON output back to the same location.

## Output naming

```
site/sketches/<sketch>/assets/<image-stem>.<pipeline-name>.json
```

Examples: `tile.edges.json`, `cardboard.edges.json`

All pipeline outputs must include a top-level `version` integer field. Increment it when the schema changes incompatibly.

## Adding a pipeline

1. Create `pipelines/<name>/` with:
   - `__init__.py` (empty)
   - `pipeline.py` — exposes `run(sketch_name, image_stem=None)`
   - `README.md` — documents the output JSON schema as a TypeScript interface

2. The CLI auto-discovers it — no registration needed.

## Pipeline contract

```python
def run(sketch_name: str, image_stem: str | None = None) -> None:
    """
    Read from sketch assets, write pipeline output back to sketch assets.
    If image_stem is None, run against all images in the sketch.
    """
```

Use `sketchbook.paths` to resolve all paths. Never hardcode sketch directories.

## Available pipelines

| name | description |
|------|-------------|
| `edges` | Canny edge detection → contours JSON. Params tuned in `playground/canny_edge_fence.py`. |
