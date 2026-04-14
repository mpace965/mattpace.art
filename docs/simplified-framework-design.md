# Simplified Framework Design

The Sketchbook framework is being redesigned around a single principle: **normal Python is the
interface**. Functions are computation units. Values are values. The framework provides a minimal
protocol — a handful of decorators and functions — and stays out of everything else.

## What changes

The current design requires sketch authors to subclass `Sketch`, subclass `PipelineStep`,
implement `setup()` and `process()`, and use a custom DSL (`self.source()`, `self.pipe()`,
`self.add()`). The new design replaces all of this with decorated functions and function calls.

## The protocol surface

The framework provides exactly:

- `@sketch` — marks a function as a sketch, carries display metadata
- `@step` — marks a function as a pipeline step, enables deferred execution
- `source(path, loader)` — declares a watched file input
- `output(node, name, presets=[])` — declares a build output
- `Param(...)` — used inside `Annotated[T, Param(...)]` to annotate tunable parameters
- `SketchContext` — injected settings object carrying `mode` and future sketch-level config

## Value types

Value types (e.g. `Image`) are **userland**, not framework. The framework duck-types them: it
looks for `to_preview_bytes()`, `to_output_bytes()`, and `extension`. If a value has these, the
framework knows how to write it to disk and serve it in the browser. Provide `to_html(url) -> str`
to customise how the value renders in the dev UI; without it the framework defaults to `<img>`.

## The DAG

The DAG still exists — it's needed for partial re-execution. But it's invisible. `@step` functions
return proxy objects when called from a sketch context. The proxy carries type information and
records the DAG edge. Step implementations receive real values; the proxy is unwrapped before
execution.

## What disappears

`PipelineStep`, `Sketch`, `setup()`, `process()`, `add_input()`, `add_param()`, `Postprocess`,
and the `self.*` DSL. The OpenCV dependency leaves the framework entirely.

## What it looks like

```python
@sketch(date="2026-03-09")
def cardboard():
    """Greyscale cardboard texture with a grid of inverted circles."""
    photo = source("assets/cardboard.jpg", loader=lambda p: Image(cv2.imread(str(p))))
    mask = circle_grid_mask(photo)
    blended = difference_blend(photo, mask)
    return output(blended, SITE_BUNDLE, presets=["nine"])


@step
def circle_grid_mask(
    image: Image,
    *,
    count: Annotated[int, Param(min=1, max=20, step=1, debounce=150)] = 3,
    radius: Annotated[float, Param(min=0.0, max=1.0, step=0.01, debounce=150)] = 0.75,
) -> Image:
    """Draw a uniform grid of filled white circles on a black background."""
    ...


@step
def difference_blend(image: Image, mask: Image) -> Image:
    """Return the per-pixel absolute difference of image and mask."""
    return Image(cv2.absdiff(image.data, mask.data))
```
