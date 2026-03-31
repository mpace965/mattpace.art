# PNG compression for build output

## Problem

`Image.to_bytes()` encodes with `compress_level=0` (no compression). This was set deliberately
to keep workdir writes fast during dev iteration — the workdir is ephemeral and speed matters
there. But the builder calls the same `to_bytes()` when baking final output, so deployed images
are uncompressed: ~11 MB per PNG.

PNG compression is always lossless. `compress_level` only controls CPU time vs file size — there
are no quality tradeoffs, no visible artifacts at any level.

---

## Solution: two-tier encoding

| Site                | Level | Rationale                                    |
|---------------------|-------|----------------------------------------------|
| Workdir (executor)  | 0     | Fast; ephemeral; nobody downloads these      |
| Build output (builder) | 9  | Slowest but smallest; baked once per deploy  |

Level 9 is PNG's maximum deflate effort. For typical creative output (photos, blended images,
textures) this cuts file sizes by 50–70 % vs level 0 with zero quality loss.

No new dependencies. The `compress_level` parameter is already accepted by Pillow's `save()`.

---

## Implementation

### 1. Add `compress_level` to `Image.to_bytes()`

`PipelineValue.to_bytes()` is the abstract interface. The parameter only makes sense for
image types so it stays on `Image`, not on the abstract base. The builder will type-check.

```python
# core/types.py — Image.to_bytes()
def to_bytes(self, compress_level: int = 0) -> bytes:
    """Encode the image array as PNG bytes using Pillow."""
    pil = PILImage.fromarray(self.data)
    buf = io.BytesIO()
    pil.save(buf, format="PNG", compress_level=compress_level)
    return buf.getvalue()
```

The executor (`Path(node.workdir_path).write_bytes(node.output.to_bytes())`) calls with no
argument, so it continues to use level 0. No change needed there.

### 2. Builder passes `compress_level=9`

In `builder.py`'s `_snapshot_variants`, import `Image` and encode with max compression:

```python
from sketchbook.core.types import Image

# inside _snapshot_variants, where the output is written:
if bundle_node.output is not None:
    dest = sketch_output_dir / f"{preset_name}.png"
    output = bundle_node.output
    encoded = output.to_bytes(compress_level=9) if isinstance(output, Image) else output.to_bytes()
    dest.write_bytes(encoded)
```

The `isinstance` guard means non-image `PipelineValue` types (SVGData, RawData) work
unchanged when future bundle types are supported.

---

## Definition of done

- [ ] `Image.to_bytes()` accepts an optional `compress_level: int = 0` parameter
- [ ] Workdir writes in the executor are unchanged (default level 0)
- [ ] Builder bakes output with `compress_level=9`
- [ ] Unit test: `to_bytes(compress_level=9)` produces smaller output than `to_bytes(compress_level=0)` for a noisy image
- [ ] Unit test: builder bakes with level 9 (mock or spy on `to_bytes`)
- [ ] All existing tests pass
- [ ] `mise run lint` passes

---

## Outer loop — acceptance test

### Step 1: write `tests/acceptance/test_10_png_compression.py`

```python
"""Acceptance test 10: build output uses maximum PNG compression.

Acceptance criteria:
    Image.to_bytes() respects compress_level.
    The builder bakes output with compress_level=9.
    Deployed images are smaller than uncompressed equivalents.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from sketchbook.core.types import Image


def _noisy_image() -> Image:
    rng = np.random.default_rng(0)
    return Image(rng.integers(0, 256, (256, 256, 3), dtype=np.uint8))


def test_compress_level_9_smaller_than_level_0() -> None:
    """Higher compress_level produces smaller PNG bytes."""
    img = _noisy_image()
    assert len(img.to_bytes(compress_level=9)) < len(img.to_bytes(compress_level=0))


def test_compress_level_9_still_valid_png() -> None:
    """Compressed output is still a valid PNG (magic bytes intact)."""
    img = _noisy_image()
    assert img.to_bytes(compress_level=9)[:8] == b"\x89PNG\r\n\x1a\n"


def test_compress_level_0_lossless(tmp_path: Path) -> None:
    """Round-trip through level 0 and level 9 produces identical pixel data."""
    from PIL import Image as PILImage

    img = _noisy_image()
    for level in (0, 9):
        data = img.to_bytes(compress_level=level)
        rt = np.array(PILImage.open(__import__("io").BytesIO(data)))
        assert np.array_equal(rt, img.data), f"Round-trip failed at compress_level={level}"


def test_builder_bakes_with_max_compression(tmp_path: Path) -> None:
    """Builder output is smaller than the same image encoded at level 0."""
    import cv2

    from sketchbook import Sketch
    from sketchbook.core.types import Image
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

    class _CompSketch(Sketch):
        name = "Compression Test"
        description = "Tests that the builder uses max PNG compression."
        date = "2026-03-31"

        _source_loader = staticmethod(lambda p: Image(cv2.imread(str(p))))

        def build(self) -> None:
            photo = self.source("photo", "assets/photo.png")
            photo.pipe(OutputBundle, bundle_name="gallery")

    output_dir = tmp_path / "dist"
    build_bundle(
        {"comp_sketch": _CompSketch},
        sketches_dir=tmp_path / "sketches",
        output_dir=output_dir,
        bundle_name="gallery",
    )

    baked = output_dir / "comp-sketch" / "default.png"
    assert baked.exists()

    uncompressed_size = len(Image(noisy).to_bytes(compress_level=0))
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
- `test_compress_level_9_smaller_than_level_0` — `to_bytes()` does not yet accept `compress_level`
- `test_compress_level_9_still_valid_png` — same
- `test_compress_level_0_lossless` — same
- `test_builder_bakes_with_max_compression` — same root cause

---

## Inner loop 1 — `Image.to_bytes()` accepts `compress_level`

### Step 3: add unit test

Add to `tests/unit/test_types.py`:

```python
def test_image_to_bytes_compress_level_9_smaller_than_0() -> None:
    """compress_level=9 produces fewer bytes than compress_level=0 for noisy data."""
    rng = np.random.default_rng(42)
    data = rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)
    img = Image(data)
    assert len(img.to_bytes(compress_level=9)) < len(img.to_bytes(compress_level=0))


def test_image_to_bytes_compress_level_default_is_zero() -> None:
    """Default compress_level produces the same output as explicit level 0."""
    img = Image(np.zeros((8, 8, 3), dtype=np.uint8))
    assert img.to_bytes() == img.to_bytes(compress_level=0)


def test_image_to_bytes_all_levels_lossless() -> None:
    """Every compress_level is lossless — pixel data survives a round-trip."""
    from PIL import Image as PILImage
    import io

    rng = np.random.default_rng(7)
    data = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
    img = Image(data)
    for level in (0, 6, 9):
        rt = np.array(PILImage.open(io.BytesIO(img.to_bytes(compress_level=level))))
        assert np.array_equal(rt, data), f"Round-trip failed at level {level}"
```

### Step 4: run unit test — confirm RED

```
uv run pytest tests/unit/test_types.py -v -k "compress"
```

Expected: all three fail — `to_bytes()` does not accept `compress_level` yet.

### Step 5: implement

In `framework/src/sketchbook/core/types.py`, add the `compress_level` parameter:

```python
def to_bytes(self, compress_level: int = 0) -> bytes:
    """Encode the image array as PNG bytes using Pillow."""
    pil = PILImage.fromarray(self.data)
    buf = io.BytesIO()
    pil.save(buf, format="PNG", compress_level=compress_level)
    return buf.getvalue()
```

### Step 6: run unit tests — confirm GREEN

```
uv run pytest tests/unit/test_types.py -v
```

All tests must pass.

---

## Inner loop 2 — builder uses `compress_level=9`

### Step 7: add unit test for builder

Add to `tests/unit/test_builder.py`:

```python
def test_builder_output_smaller_than_uncompressed(tmp_path: Path) -> None:
    """Baked PNG is smaller than the equivalent uncompressed PNG."""
    import cv2
    import numpy as np

    from sketchbook import Sketch
    from sketchbook.core.types import Image
    from sketchbook.site.builder import build_bundle
    from sketchbook.steps.output_bundle import OutputBundle

    sketch_dir = tmp_path / "sketches" / "comp_sketch"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)

    rng = np.random.default_rng(99)
    noisy = rng.integers(0, 256, (128, 128, 3), dtype=np.uint8)
    cv2.imwrite(str(assets_dir / "photo.png"), noisy)

    presets_dir = sketch_dir / "presets"
    presets_dir.mkdir()
    (presets_dir / "default.json").write_text("{}")

    class _CompSketch(Sketch):
        name = "Builder Compression"
        description = ""
        date = "2026-03-31"
        _source_loader = staticmethod(lambda p: Image(cv2.imread(str(p))))

        def build(self) -> None:
            self.source("photo", "assets/photo.png").pipe(OutputBundle, bundle_name="test")

    output_dir = tmp_path / "dist"
    build_bundle(
        {"comp_sketch": _CompSketch},
        sketches_dir=tmp_path / "sketches",
        output_dir=output_dir,
        bundle_name="test",
    )

    baked = output_dir / "comp-sketch" / "default.png"
    assert baked.exists()
    uncompressed_size = len(Image(noisy).to_bytes(compress_level=0))
    assert baked.stat().st_size < uncompressed_size
```

### Step 8: run unit test — confirm RED

```
uv run pytest tests/unit/test_builder.py -v -k "compress"
```

Expected: fails because builder still calls `to_bytes()` with no arguments (level 0).

### Step 9: implement — update builder

In `framework/src/sketchbook/site/builder.py`:

1. Add import: `from sketchbook.core.types import Image`
2. Update the write in `_snapshot_variants`:

```python
if bundle_node.output is not None:
    dest = sketch_output_dir / f"{preset_name}.png"
    output = bundle_node.output
    encoded = (
        output.to_bytes(compress_level=9)
        if isinstance(output, Image)
        else output.to_bytes()
    )
    dest.write_bytes(encoded)
```

### Step 10: run unit tests — confirm GREEN

```
uv run pytest tests/unit/test_builder.py -v
```

All tests must pass.

---

## Outer loop — acceptance test green

### Step 11: run acceptance test

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

## Notes

**Why not change the workdir default to 6?** The workdir is ephemeral and written on every
pipeline execution during dev. Level 0 is measurably faster for large images and nobody downloads
these files. Keep them fast.

**Why 9 and not 6?** Build is a one-shot operation. Extra seconds of compression CPU time are
invisible. Level 9 squeezes every byte out of lossless PNG — the only cost is build time.

**Will this be enough?** For creative output with large uniform regions or smooth gradients,
level 9 PNG is very effective. For photorealistic images with high entropy (noise, film grain,
complex textures), PNG compresses poorly at any level — even level 9 may only cut 20–30 % vs
level 0. If file sizes are still unacceptable after this increment, the next step is lossless
WebP (`format="WEBP", lossless=True` in Pillow), which typically halves PNG file sizes with
zero quality loss. That would require updating `Image.extension` and `Image.mime_type`, and
adding WebP support to the browser preview endpoint — a separate increment.
