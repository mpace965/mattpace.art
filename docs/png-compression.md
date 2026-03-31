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
- [ ] Unit tests pass
- [ ] All existing tests pass
- [ ] `mise run lint` passes

---

## Tests

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
    import io as _io
    from PIL import Image as PILImage

    rng = np.random.default_rng(7)
    data = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
    for level in (0, 6, 9):
        img = Image(data, compress_level=level)
        rt = np.array(PILImage.open(_io.BytesIO(img.to_bytes())))
        assert np.array_equal(rt, data), f"Round-trip failed at compress_level={level}"
```

---

## Usage pattern

During iteration (default — fast workdir writes):

```python
return Image(result_array)
```

When ready to publish (in a terminal step before OutputBundle):

```python
return Image(src.data, compress_level=9)
```

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
