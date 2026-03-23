# Decoupling `Image` from the framework

## Problem

`Image` in `core/types.py` currently does three things:

1. **Type marker** — used in `add_input("image", Image)` to declare and validate DAG wiring
2. **UI hint** — the server needs to know how to render a node's output in the browser
3. **Intermediate storage** — the executor writes results to `.workdir/node_id.png`

It also has `load` and `save` methods that call `cv2.imread` / `cv2.imwrite`, pulling
`opencv-python-headless` in as a runtime framework dependency. This is the wrong layering:
opencv is a computer vision library and belongs in userland (sketches), not in the engine.

Two places in the framework call into this I/O:

- `Image.load` is called by `SourceFile.process()` in `steps/source.py`
- `Image.save` is called by the executor in `core/executor.py` line 82:
  `node.output.save(node.workdir_path)`

The workdir path itself is also hardcoded as `.png` in `Sketch._register_node`:
`workdir_path = self._workdir / f"{node_id}.png"`

This hardcoding prevents the framework from ever supporting non-image output types
without surgery on `Sketch`.

---

## The two kinds of I/O

There are two distinct I/O concerns that the current design conflates:

| Kind | Owner | Examples |
|---|---|---|
| **Framework-internal** — writing workdir intermediates | Framework, via a serialization interface on each value type | `node.output.to_bytes()` in the executor |
| **User-facing** — loading source assets, writing final outputs | Userland (sketches) | `cv2.imread`, exporting to TIFF |

`Image.load` and `Image.save` are user-facing I/O. They don't belong on the framework type.
The framework only needs a way to serialize values for its own internal workdir writes —
and that interface should work for any pipeline value type, not just images.

---

## The full vision: `PipelineValue`

The natural abstraction is an abstract base class that every pipeline value type implements:

```python
class PipelineValue:
    """Base class for all values that flow between pipeline steps."""

    extension: str   # workdir filename extension — "png", "svg", "json"
    mime_type: str   # MIME type for the browser preview endpoint

    def to_bytes(self) -> bytes:
        """Serialize to bytes for workdir storage."""
        ...

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        """Deserialize from bytes."""
        ...
```

The executor uses `to_bytes()` to write workdir intermediates. The server preview endpoint
uses `mime_type` to serve the correct content type. Neither needs to know what the value
actually contains.

`from_bytes()` rounds out the serialisation interface and is introduced in Increment B
alongside `SVGData` and `RawData`. It is not called by anything in Increment A.

### Concrete types

**`Image`** wraps a numpy `ndarray`. For `to_bytes()`, Pillow is the natural lightweight
codec — pure image I/O, no computer vision, far smaller than opencv. This replaces the
only remaining legitimate use of cv2 inside the framework.

```python
class Image(PipelineValue):
    extension = "png"
    mime_type = "image/png"

    def __init__(self, data: np.ndarray) -> None:
        self.data = data

    def to_bytes(self) -> bytes:
        """Encode as PNG using Pillow."""
        from PIL import Image as PILImage
        pil = PILImage.fromarray(self.data)
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        return buf.getvalue()

    @classmethod
    def from_bytes(cls, data: bytes) -> Image:
        from PIL import Image as PILImage
        import numpy as np
        pil = PILImage.open(io.BytesIO(data))
        return cls(np.array(pil))
```

Pillow is added to the framework's runtime dependencies. opencv is moved to dev-only.

**`SVGData`** wraps an SVG string. No codec needed — serialization is just UTF-8 encode/decode.

```python
class SVGData(PipelineValue):
    extension = "svg"
    mime_type = "image/svg+xml"

    def __init__(self, markup: str) -> None:
        self.markup = markup

    def to_bytes(self) -> bytes:
        return self.markup.encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> SVGData:
        return cls(data.decode())
```

**`RawData`** wraps arbitrary JSON-serialisable data. Useful for passing structured values
(arrays, dicts, numbers) between steps when images aren't the right currency.

```python
class RawData(PipelineValue):
    extension = "json"
    mime_type = "application/json"

    def __init__(self, value: Any) -> None:
        self.value = value

    def to_bytes(self) -> bytes:
        return json.dumps(self.value).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> RawData:
        return cls(json.loads(data.decode()))
```

SVG and raw data are simpler to add than images precisely because they need no codec.

---

## Incremental approach

The work breaks into two increments:

### Increment A — strip opencv from the framework (do this first)

1. Introduce `PipelineValue` base class in `core/types.py` with `extension`, `mime_type`,
   and abstract `to_bytes()`. (`from_bytes()` is stubbed but not yet called by anything.)

2. Make `Image` a `PipelineValue` subclass. `extension = "png"`, `mime_type = "image/png"`.
   Implement `to_bytes()` using Pillow. Remove `load`, `save`, and `import cv2`.

3. Add `Pillow` to runtime dependencies. Move `opencv-python-headless` to dev dependencies.

4. Update the executor: replace `node.output.save(node.workdir_path)` with
   `Path(node.workdir_path).write_bytes(node.output.to_bytes())`. The workdir path remains
   `.png` (from `Image.extension`) for now — making it dynamic is Increment B's job.

5. Make `SourceFile` accept a `loader: Callable[[Path], Any]` parameter. The step holds
   the path (required by the file watcher) and delegates loading to the callable.
   `Sketch.source()` forwards it through via a `_source_loader` class attribute on `Sketch`.

6. Update `test_types.py` — remove load/save tests; add tests for `PipelineValue` interface
   on `Image` (`extension`, `mime_type`, `to_bytes()` round-trip).

7. Update sketches: set `_source_loader` using `cv2.imread` directly. Since sketches
   already import cv2, this is a one-liner.

### Increment B — multi-type support and dynamic workdir paths

1. Add `SVGData` and `RawData` as concrete `PipelineValue` types. Implement `from_bytes()`
   on all three types.

2. Make the workdir path extension dynamic: derive it from the step's declared output type
   rather than hardcoding `.png` in `Sketch._register_node`.

3. Update the server preview endpoint to serve `value.to_bytes()` with `value.mime_type`
   rather than assuming PNG.

4. Add `add_input` type validation that checks `issubclass(actual_type, expected_type)`
   so the DAG wiring system works across all value types.

---

## What the framework owns vs. userland

After both increments:

| Concern | Owner |
|---|---|
| `PipelineValue` base class and `Image`, `SVGData`, `RawData` types | Framework |
| Workdir writes (`to_bytes`) | Framework (via `PipelineValue` interface) |
| Browser preview serving (`mime_type`) | Framework |
| Loading source assets from disk (`cv2.imread`, etc.) | Sketches |
| Writing final outputs (export to TIFF, PDF, etc.) | Sketches |
| opencv, or any image library beyond Pillow | Sketches |

The framework stays generic. Sketches own their image-library choices.
