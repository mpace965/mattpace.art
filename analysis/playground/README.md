# playground

A space for one-off image processing experiments. Scripts here are committed as reference but are not productionized pipelines.

## Usage

Write a Python script here and run it with:

```bash
uv run python playground/my_experiment.py
```

Use the shared utilities to access sketch assets:

```python
from sketchbook.paths import sketch_assets_dir, sketch_image_paths, find_image

# all images for a sketch
images = sketch_image_paths("tree-bark-tile")

# a specific image by stem
img = find_image("cardboard", "cardboard")
```

Write intermediate or experimental output to `/tmp` — never to `site/sketches/` or anywhere inside this repo.

## Graduating to a pipeline

When an experiment is ready to productionize, move it to `pipelines/<name>/pipeline.py` following the conventions in `pipelines/README.md`.
