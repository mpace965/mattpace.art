# Execution Profiles — Implementation Plan

## What this increment does

Introduces `ExecutionProfile` (a frozen dataclass carrying `draft_scale` and `compress_level`) and `ProfileRegistry` (a cascade lookup keyed by mode name). `Sketch.__init__` gains a `mode` parameter, calls `execution_profiles()` to merge sketch overrides, resolves the correct profile, and passes it into `build(profile)`. `OutputBundle` accepts a `compress_level` and stamps it onto the output image. The sketch author wires values explicitly in `build()`.

---

## Mental model

- **Profile**: a bag of execution-quality values (`draft_scale`, `compress_level`). Nothing more.
- **Registry**: maps mode name → profile, with a three-level cascade.
- **Mode**: a string — `"dev"` or `"build"`. Passed in by the execution context (server for dev, builder for build).
- **Sketch author's job**: receive the profile in `build()`, use `profile.draft_scale` and `profile.compress_level` explicitly. Nothing is automatic.

---

## Cascade

```
resolve(mode)
  1. sketch[mode]            → found → return (no warning)
  2. framework_defaults[mode] → found → log.warning(...) → return
  3. framework_defaults["base"] → found → log.warning(...) → return
  4.                         → raise RuntimeError (framework bug)
```

Framework ships three hard-coded defaults:

| Mode    | draft_scale | compress_level |
|---------|-------------|----------------|
| `base`  | 1.0         | 0              |
| `dev`   | 1.0         | 0              |
| `build` | 1.0         | 6              |

Sketch authors override by returning a dict from `execution_profiles()`. Any key not overridden falls through to the framework default.

---

## Files to create

### `framework/src/sketchbook/core/profile.py`

```python
@dataclass(frozen=True)
class ExecutionProfile:
    draft_scale: float
    compress_level: int

class ProfileRegistry:
    _FRAMEWORK_DEFAULTS: ClassVar[dict[str, ExecutionProfile]] = {
        "base":  ExecutionProfile(draft_scale=1.0, compress_level=0),
        "dev":   ExecutionProfile(draft_scale=1.0, compress_level=0),
        "build": ExecutionProfile(draft_scale=1.0, compress_level=6),
    }

    def __init__(self, sketch_profiles: dict[str, ExecutionProfile]) -> None:
        self._sketch = sketch_profiles

    def resolve(self, mode: str) -> ExecutionProfile:
        # cascade: sketch → framework mode → base → fail
        ...
```

### `framework/tests/unit/test_profile.py`

Unit tests (all must be written before implementation):

- `test_resolve_sketch_override_wins` — sketch provides "dev"; registry returns it; no warning.
- `test_resolve_falls_back_to_framework_default_with_warning` — sketch has no "dev"; framework has "dev"; resolve warns and returns framework value.
- `test_resolve_unknown_mode_falls_back_to_base_with_warning` — unknown mode "foobar"; falls back to "base"; warns.
- `test_resolve_hard_fails_if_base_missing` — subclass with empty `_FRAMEWORK_DEFAULTS`; raises `RuntimeError`.
- `test_framework_ships_dev_profile` — sanity-check that `"dev"` is in `_FRAMEWORK_DEFAULTS`.
- `test_framework_ships_build_profile` — sanity-check that `"build"` is in `_FRAMEWORK_DEFAULTS`.
- `test_execution_profile_is_frozen` — mutating a field raises `FrozenInstanceError`.

---

## Files to modify

### `framework/src/sketchbook/core/sketch.py`

**`Sketch.__init__`** — add `mode: str = "dev"` parameter. Before calling `build()`:

```python
sketch_profiles = self.execution_profiles()
self._profile_registry = ProfileRegistry(sketch_profiles)
profile = self._profile_registry.resolve(mode)
self.build(profile)
```

**`Sketch.execution_profiles()`** — new template method:

```python
def execution_profiles(self) -> dict[str, ExecutionProfile]:
    """Return sketch-level profile overrides keyed by mode name."""
    return {}
```

**`Sketch.build()`** — change signature:

```python
def build(self, profile: ExecutionProfile) -> None:
    """Override to define the pipeline. Use profile.draft_scale and profile.compress_level."""
    raise NotImplementedError(f"{type(self).__name__} must implement build()")
```

**`Sketch.output_bundle()`** — add `compress_level: int = 0` parameter; pass through to `OutputBundle`:

```python
def output_bundle(
    self,
    node: _ManagedNode,
    bundle_name: str,
    presets: list[str] | None = None,
    compress_level: int = 0,
) -> _ManagedNode:
    ...
    managed = self._register_node(
        OutputBundle(bundle_name, presets=presets, compress_level=compress_level), node_id
    )
```

Add import: `from sketchbook.core.profile import ExecutionProfile, ProfileRegistry`

### `framework/src/sketchbook/steps/output_bundle.py`

Add `compress_level: int = 0` to `__init__`. In `process()`, stamp it onto the returned image:

```python
def __init__(self, bundle_name: str, presets: list[str] | None = None, compress_level: int = 0) -> None:
    self.bundle_name = bundle_name
    self.presets = presets
    self.compress_level = compress_level
    super().__init__()

def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Any:
    img = inputs["image"]
    return Image(img.data, compress_level=self.compress_level)
```

Import `Image` from `sketchbook.core.types`.

### `framework/src/sketchbook/server/registry.py`

In `_load_sketch_lazy()`, pass `mode="dev"`:

```python
instance = cls(sketch_dir, mode="dev")
```

### `framework/src/sketchbook/bundle/builder.py`

In `_build_variant()`, pass `mode="build"`:

```python
sketch = task.sketch_cls(task.sketch_dir, mode="build")
```

In `_discover_sketch()`, pass `mode="build"`:

```python
sketch = sketch_cls(sketch_dir, mode="build")
```

---

## Test sketch updates

Every inline test sketch in `framework/tests/unit/test_sketch.py` has `def build(self) -> None:`. All must be updated to `def build(self, profile: ExecutionProfile) -> None:`. The `profile` argument is unused in the existing test sketches — that's fine.

All test classes in `test_sketch.py` that define `build()` need the signature change. Count: roughly 12 inner classes. The test assertions don't change — only the method signature.

Add `from sketchbook.core.profile import ExecutionProfile` to the test file's imports.

---

## Sketch updates (userland)

All four sketches have `def build(self) -> None:`. Update signature to `def build(self, profile: ExecutionProfile) -> None:`. The `profile` argument can be unused initially — the point is to stop them from breaking.

**Recommended improvement for `cardboard_stripes`**: replace the hardcoded `compress_level=9` in `DifferenceBlend.process()` with `profile.compress_level` wired through `output_bundle()`:

```python
def build(self, profile: ExecutionProfile) -> None:
    photo = self.source("photo", "assets/cardboard.jpg", loader=lambda p: Image(cv2.imread(str(p))))
    mask = photo.pipe(StripesMask)
    blended = self.add(DifferenceBlend, inputs={"image": photo, "mask": mask})
    self.output_bundle(blended, SITE_BUNDLE, presets=["three", "steps"],
                       compress_level=profile.compress_level)
```

And remove `compress_level=9` from `DifferenceBlend.process()` (that hardcoding belongs in the profile now).

`cardboard_stripes` can also override profiles to get the old behavior back in build mode:

```python
def execution_profiles(self) -> dict[str, ExecutionProfile]:
    return {"build": ExecutionProfile(draft_scale=1.0, compress_level=9)}
```

Other sketches (cardboard, fence-torn-paper, kick-polygons): update signature only; no behavior changes needed unless desired.

---

## Acceptance test

**`framework/tests/acceptance/test_execution_profiles.py`**

Scenarios to cover end-to-end (acceptance test written first):

1. **Profile reaches `build()`** — A sketch that records `profile.compress_level` during `build()`. Instantiate with `mode="build"`. Assert the stored value equals the framework "build" default (`6`).

2. **Sketch override is applied** — A sketch that overrides `"build"` profile with `compress_level=9`. Instantiate with `mode="build"`. Assert the stored value is `9`.

3. **OutputBundle stamps compress_level** — Execute a minimal pipeline with an `OutputBundle(compress_level=6)`. Call `.to_bytes()` on the output image. The result must differ from the same image with `compress_level=0` (different byte length). This confirms `compress_level` is wired end-to-end.

4. **Dev mode uses dev profile** — Instantiate a profile-aware sketch with `mode="dev"`. Assert `compress_level == 0`.

---

## Order of work (GOOS double-loop)

### Outer loop — acceptance test

Write `test_execution_profiles.py` first. All four scenarios will fail immediately (no profile module yet).

### Inner loop — unit by unit

**Step 1**: `ExecutionProfile` dataclass
- Write `test_execution_profile_is_frozen`
- Implement `ExecutionProfile` in `core/profile.py`

**Step 2**: `ProfileRegistry` cascade
- Write all `test_resolve_*` and `test_framework_ships_*` unit tests
- Implement `ProfileRegistry` with `_FRAMEWORK_DEFAULTS` and `resolve()`

**Step 3**: `Sketch.__init__` + `execution_profiles()` + `build(profile)`
- Write unit test: a sketch with a mode override records the resolved profile (add to `test_sketch.py`)
- Update `Sketch` class — add `mode`, call `execution_profiles()`, resolve, pass to `build()`
- Update `build()` base signature
- Update all inline test sketches in `test_sketch.py` to `build(self, profile)`

**Step 4**: `OutputBundle` compression
- Write unit test: `OutputBundle` with `compress_level=6` returns `Image` with `compress_level=6`
- Implement change to `OutputBundle.process()`
- Write unit test: `Sketch.output_bundle(compress_level=6)` creates node with correct `compress_level`

**Step 5**: Execution contexts
- Update `registry._load_sketch_lazy` to pass `mode="dev"`
- Update `builder._build_variant` and `_discover_sketch` to pass `mode="build"`

**Step 6**: Sketch userland updates
- Update all four sketch `build()` signatures
- Remove `compress_level=9` from `cardboard_stripes.DifferenceBlend.process()`
- Add `execution_profiles()` override + `compress_level=profile.compress_level` to `cardboard_stripes.output_bundle()` call

### Refactor pass

Once acceptance test is green:
- Check that warning log messages are clear and useful
- Verify `mise run lint` passes (Ruff)

---

## Definition of done checklist

From the design doc:

- [ ] `ExecutionProfile` frozen dataclass with `draft_scale` and `compress_level`
- [ ] `ProfileRegistry` with cascade lookup and appropriate warnings/failures
- [ ] Framework ships defaults: base, dev, build profiles
- [ ] `Sketch.execution_profiles()` template method; framework merges overrides at construction
- [ ] Execution context resolves and passes profile into `build()`
- [ ] `OutputBundle` accepts `compress_level` from the profile
- [ ] Unit tests cover cascade fallback, warning behaviour, and hard failure
- [ ] `mise run lint` passes

Additional:
- [ ] `cardboard_stripes` no longer hardcodes `compress_level=9` in step code
- [ ] All existing acceptance tests still pass
- [ ] `mode="dev"` default means existing test code that calls `SketchClass(tmp_path)` without a mode still works
