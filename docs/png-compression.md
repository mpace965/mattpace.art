# PNG compression

## Problem

`Image.to_bytes()` encodes with `compress_level=0` (no compression). This was set deliberately
to keep workdir writes fast during dev iteration — the workdir is ephemeral and speed matters
there. The builder calls the same `to_bytes()` when baking final output, so deployed images
are uncompressed: ~11 MB per PNG.

PNG compression is always lossless. `compress_level` only controls CPU time vs file size — there
are no quality tradeoffs, no visible artifacts at any level.

---

## Solution: `compress_level` on `Image`

`Image` carries its own `compress_level` as a constructor argument (default 0). `to_bytes()`
uses it — no parameters on the method, no changes to `PipelineValue`, no special cases in the
builder. The framework stays generic throughout.

```python
class Image(PipelineValue):
    def __init__(self, data: np.ndarray, compress_level: int = 0) -> None:
        self.data = data
        self.compress_level = compress_level

    def to_bytes(self) -> bytes:
        pil = PILImage.fromarray(self.data)
        buf = io.BytesIO()
        pil.save(buf, format="PNG", compress_level=self.compress_level)
        return buf.getvalue()
```

The executor writes `node.output.to_bytes()` — no change. The builder writes
`bundle_node.output.to_bytes()` — no change. A sketch that wants compressed output
constructs its `Image` values with `compress_level=9` in whatever terminal step it uses.
Iteration mode and publishing mode are just different `compress_level` values in userland.

No new dependencies. The `compress_level` parameter is already accepted by Pillow's `save()`.

---

## Definition of done

- [ ] `Image.__init__` accepts `compress_level: int = 0` and stores it on `self`
- [ ] `Image.to_bytes()` uses `self.compress_level` (signature unchanged — no parameters)
- [ ] All existing tests pass
- [ ] Unit tests: `compress_level` is stored, respected, and lossless at all levels
- [ ] `mise run lint` passes

---

## Outer loop — acceptance test

### Step 1: write `tests/acceptance/test_10_png_compression.py`

```python
"""Acceptance test 10: Image carries its own compress_level.

Acceptance criteria:
    Image accepts a compress_level constructor argument.
    to_bytes() encodes using that level — higher level produces smaller output.
    All levels are lossless — pixel data survives a round-trip.
    A sketch that constructs Image(data, compress_level=9) produces compressed output
    when baked by the builder.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

from sketchbook.core.types import Image


def _noisy_image(compress_level: int = 0) -> Image:
    rng = np.random.default_rng(0)
    return Image(rng.integers(0, 256, (256, 256, 3), dtype=np.uint8), compress_level=compress_level)


def test_image_compress_level_stored() -> None:
    """compress_level is stored on the Image instance."""
    img = Image(np.zeros((4, 4, 3), dtype=np.uint8), compress_level=9)
    assert img.compress_level == 9


def test_image_default_compress_level_is_zero() -> None:
    """Default compress_level is 0."""
    img = Image(np.zeros((4, 4, 3), dtype=np.uint8))
    assert img.compress_level == 0


def test_compress_level_9_smaller_than_level_0() -> None:
    """Higher compress_level produces smaller PNG bytes."""
    assert len(_noisy_image(compress_level=9).to_bytes()) < len(_noisy_image(compress_level=0).to_bytes())


def test_compress_level_9_still_valid_png() -> None:
    """Compressed output is still a valid PNG (magic bytes intact)."""
    assert _noisy_image(compress_level=9).to_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_all_compress_levels_lossless() -> None:
    """Every compress_level is lossless — pixel data survives a round-trip."""
    from PIL import Image as PILImage

    rng = np.random.default_rng(0)
    data = rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)
    for level in (0, 6, 9):
        img = Image(data, compress_level=level)
        rt = np.array(PILImage.open(io.BytesIO(img.to_bytes())))
        assert np.array_equal(rt, data), f"Round-trip failed at compress_level={level}"


def test_builder_respects_compress_level_9(tmp_path: Path) -> None:
    """A sketch that wraps output in Image(data, compress_level=9) produces a smaller baked file."""
    import cv2
    from typing import Any

    from sketchbook import Sketch
    from sketchbook.core.executor import execute
    from sketchbook.core.step import PipelineStep
    from sketchbook.site.builder import build_bundle
    from sketchbook.steps.output_bundle import OutputBundle

    sketch_dir = tmp_path / "sketches" / "comp_sketch"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)

    rng = np.random.default_rng(1)
    noisy = rng.integers(0, 256, (256, 256, 3), dtype=np.uint8)
    cv2.imwrite(str(assets_dir / "photo.png"), noisy)

    presets_dir = sketch_dir / "presets"
    presets_dir.mkdir()
    (presets_dir / "default.json").write_text("{}")

    class _CompressForPublish(PipelineStep):
        """Re-wrap the input Image with compress_level=9."""

        def setup(self) -> None:
            self.add_input("image", type=object)

        def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
            src: Image = inputs["image"]
            return Image(src.data, compress_level=9)

    class _CompSketch(Sketch):
        name = "Compression Test"
        description = "Tests that compress_level=9 on Image flows through to the builder."
        date = "2026-03-31"

        _source_loader = staticmethod(lambda p: Image(cv2.imread(str(p))))

        def build(self) -> None:
            photo = self.source("photo", "assets/photo.png")
            compressed = photo.pipe(_CompressForPublish)
            compressed.pipe(OutputBundle, bundle_name="gallery")

    output_dir = tmp_path / "dist"
    build_bundle(
        {"comp_sketch": _CompSketch},
        sketches_dir=tmp_path / "sketches",
        output_dir=output_dir,
        bundle_name="gallery",
    )

    baked = output_dir / "comp-sketch" / "default.png"
    assert baked.exists()

    uncompressed_size = len(Image(noisy, compress_level=0).to_bytes())
    baked_size = baked.stat().st_size
    assert baked_size < uncompressed_size, (
        f"Builder output ({baked_size} bytes) is not smaller than "
        f"uncompressed ({uncompressed_size} bytes)"
    )
```

### Step 2: run the acceptance test — confirm RED

```
uv run pytest tests/acceptance/test_10_png_compression.py -v
```

Expected failures:
- `test_image_compress_level_stored` — `Image.__init__` does not yet accept `compress_level`
- `test_image_default_compress_level_is_zero` — same
- `test_compress_level_9_smaller_than_level_0` — same
- `test_compress_level_9_still_valid_png` — same
- `test_all_compress_levels_lossless` — same
- `test_builder_respects_compress_level_9` — same root cause

---

## Inner loop — `Image` carries `compress_level`

### Step 3: add unit tests

Add to `tests/unit/test_types.py`:

```python
def test_image_compress_level_default_is_zero() -> None:
    img = Image(np.zeros((4, 4, 3), dtype=np.uint8))
    assert img.compress_level == 0


def test_image_compress_level_stored() -> None:
    img = Image(np.zeros((4, 4, 3), dtype=np.uint8), compress_level=9)
    assert img.compress_level == 9


def test_image_to_bytes_uses_compress_level() -> None:
    """compress_level=9 produces fewer bytes than compress_level=0 for noisy data."""
    rng = np.random.default_rng(42)
    data = rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)
    small = Image(data, compress_level=9)
    large = Image(data, compress_level=0)
    assert len(small.to_bytes()) < len(large.to_bytes())


def test_image_to_bytes_lossless_at_all_levels() -> None:
    """All compress levels produce identical pixel data on round-trip."""
    from PIL import Image as PILImage

    rng = np.random.default_rng(7)
    data = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
    for level in (0, 6, 9):
        img = Image(data, compress_level=level)
        rt = np.array(PILImage.open(io.BytesIO(img.to_bytes())))
        assert np.array_equal(rt, data), f"Round-trip failed at compress_level={level}"
```

### Step 4: run unit tests — confirm RED

```
uv run pytest tests/unit/test_types.py -v -k "compress"
```

Expected: all four fail — `Image.__init__` does not accept `compress_level` yet.

### Step 5: implement

In `framework/src/sketchbook/core/types.py`:

```python
class Image(PipelineValue):
    """Wraps a numpy array representing an image."""

    extension = "png"
    mime_type = "image/png"

    def __init__(self, data: np.ndarray, compress_level: int = 0) -> None:
        self.data = data
        self.compress_level = compress_level

    def to_bytes(self) -> bytes:
        """Encode the image array as PNG bytes using Pillow."""
        pil = PILImage.fromarray(self.data)
        buf = io.BytesIO()
        pil.save(buf, format="PNG", compress_level=self.compress_level)
        return buf.getvalue()
```

### Step 6: run unit tests — confirm GREEN

```
uv run pytest tests/unit/test_types.py -v
```

All tests must pass. Then run the full suite to check nothing regressed:

```
uv run pytest -v
```

---

## Outer loop — acceptance test green

### Step 7: run acceptance test

```
uv run pytest tests/acceptance/test_10_png_compression.py -v
```

All tests must pass.

Then run the full suite:

```
uv run pytest -v
```

Zero failures. Run the linter:

```
uv run mise run lint
```

Zero violations.

---

## Usage pattern

During iteration (default — fast workdir writes):

```python
# in a sketch step — compress_level defaults to 0
return Image(result_array)
```

When ready to publish (in a terminal step before OutputBundle):

```python
# re-wrap with compress_level=9 just before the output node
return Image(src.data, compress_level=9)
```

This can be a reusable `CompressForPublish` step in the sketch, or inlined into whatever
final processing step the sketch already has. The framework doesn't need to know about it.

---

## Notes

**Why not a parameter on `to_bytes()`?** That would require the abstract `PipelineValue`
interface to carry it, or the builder to type-check and call image-specific methods.
Neither is clean. The encoding preference belongs to the value, not to the call site.

**Why not configure this on `OutputBundle`?** `OutputBundle` is a framework step and
shouldn't have opinions about image encoding. Compression level is a sketch concern.

**Will level 9 be enough?** For creative output with gradients, blended regions, or
limited palettes, level 9 is very effective. For high-entropy photorealistic images
(film grain, noise, complex textures), PNG compresses poorly at any level — level 9
may only cut 20–30 % vs level 0. If sizes are still unacceptable, lossless WebP
(`format="WEBP", lossless=True` in Pillow) typically halves PNG file sizes with zero
quality loss. That is a separate increment: it would require updating `Image.extension`
and `Image.mime_type`, and updating the browser preview endpoint to serve WebP.
