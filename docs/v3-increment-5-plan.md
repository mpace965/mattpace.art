# Increment 5: Sketch Cutover — Implementation Plan

## Acceptance criterion

> All four existing sketches load in the dev server using the new API. `uv run build` produces
> a valid site bundle. The framework source contains no references to `PipelineStep`, `Sketch`,
> `DAGNode`, or `DAG`. `mise run lint` passes.

---

## Current state

### What already exists (relevant to this increment)

**Framework — v3 API is fully implemented and serving:**

- `core/decorators.py` — `@step`, `@sketch`, `Param`, `SketchContext`, `SketchMeta`
- `core/building_dag.py` — `BuildingDAG`, `Proxy`, `source()`, `output()`
- `core/built_dag.py` — `BuiltDAG`, `BuiltNode`, `ParamSpec`, `InputSpec`
- `core/introspect.py` — `extract_inputs`, `extract_params`, `coerce_param`
- `core/wiring.py` — `wire_sketch`
- `core/executor_v3.py` — `execute_built`, `execute_partial_built`
- `core/presets.py` — v3 helpers: `load_active_into_built`, `save_active_from_built`, `load_preset_into_built`, `save_preset_from_built`, `list_preset_names`
- `server/fn_registry.py` — `SketchFnRegistry`
- `server/routes/v3.py` — all routes under `/v3/` prefix
- `server/tweakpane_v3.py` — `param_spec_to_tweakpane`, `built_node_to_tweakpane`
- `bundle/builder.py` — `build_bundle_fns` fully implemented
- `discovery.py` — `discover_sketch_fns` alongside `discover_sketches`
- `cli.py` — `build` command already uses `discover_sketch_fns` + `build_bundle_fns`; `dev` command still starts both old and new registries via `_dev.py`
- `sketches/types.py` — `Image` with `to_bytes(mode)`, satisfies `SketchValueProtocol`

**Userland — one v3 sketch exists as the demo:**

- `sketches/cardboard_v3/__init__.py` — `@sketch def cardboard_v3()`, uses `Image` from `sketches.types`

**Old framework still lives alongside the new:**

- `core/sketch.py`, `core/step.py`, `core/dag.py`, `core/types.py`
- `steps/source.py`, `steps/output_bundle.py`, `steps/site_output.py`, `steps/__init__.py`
- `core/params.py` — `Color`, `ParamDef`, `ParamRegistry`, `_coerce_bool`
- `server/routes/sketch.py`, `params.py`, `presets.py`, `ws.py` (old routes at root prefix)
- `server/app.py` — mounts both old router and v3 router; creates `SketchRegistry`

**Old sketches on the old API:**

- `sketches/cardboard/__init__.py` — `Cardboard(Sketch)` with `CircleGridMask`, `DifferenceBlend`, `Postprocess`
- `sketches/cardboard_stripes/__init__.py` — `CardboardStripes(Sketch)` with `StripesMask`, `DifferenceBlend`, `Postprocess`
- `sketches/fence-torn-paper/__init__.py` — `FenceTornPaper(Sketch)` with `GaussianBlur`, `CannyEdge`, `CannyComposite`, `Postprocess`; imports `Color` from `sketchbook.core.params`
- `sketches/kick-polygons/__init__.py` — `KickPolygons(Sketch)` with `Downscale(scale)`, `RadialArrange`, `Postprocess`

**Preset files (existing, old-API step IDs):**

- `cardboard/presets/nine.json` — key `circle_grid_mask_0`
- `cardboard_stripes/presets/three.json`, `steps.json` — key `stripes_mask_0`
- `fence-torn-paper/presets/default.json` — keys `gaussian_blur_0`, `canny_edge_0`, `canny_composite_0`
- `kick-polygons/presets/dress-star.json`, `fist-pinwheel.json`, `sun-pinwheel.json`, `thirteen-fist-fin.json`, `nine-spike.json`, `trefoil.json` — key `radial_arrange_0`

### What is absent

- `sketches/types.py` does not yet have `Color` — it lives in `core/params.py`
- None of the four production sketches use `@step` / `@sketch`
- The `/v3/` route prefix has not been dropped to `/`
- Old route files and the old `SketchRegistry` path in `create_app` have not been deleted
- Old framework files (`core/sketch.py`, etc.) have not been deleted
- Preset files have old-style step IDs (`circle_grid_mask_0` → `circle_grid_mask`)
- `server/routes/sketch.py`'s index handler still lists v3 sketches with `/v3/sketch/{id}` URLs

---

## GOOS double-loop

### Step 0: write the acceptance test — must fail before implementation

File: `tests/acceptance/test_cutover.py`

```
uv run pytest tests/acceptance/test_cutover.py -x
```

Expected failure: `test_all_sketches_load_in_dev_server` — `GET /sketch/cardboard` returns 404 because `cardboard` is not yet ported to v3 and the `/sketch/` prefix no longer handles old-API sketches after the route swap.

> **Important:** this test is written against the final state — route prefix dropped, old code gone, real sketches ported. It will continue to fail until all inner loops are complete.

---

### Inner loop 1: `Color` moves to `sketches/types.py`

**Failing unit test (`tests/unit/test_types_v3.py`):**

```python
from sketches.types import Color

def test_color_hex_parse():
    c = Color("#ff69b4")
    assert c.r == 255 and c.g == 105 and c.b == 180

def test_color_to_tweakpane():
    assert Color("#ff69b4").to_tweakpane() == "#ff69b4"

def test_color_to_bgr():
    assert Color("#ff0000").to_bgr() == (0, 0, 255)
```

**Implementation:**

- Copy `Color` class verbatim from `core/params.py` into `sketches/types.py`.
- `sketches/types.py` already exists (has `Image`) — append `Color` after the `Image` class.
- Do not yet delete `Color` from `core/params.py` — `fence-torn-paper` still imports it there until loop 4.

**Checkpoint:** `uv run pytest tests/unit/test_types_v3.py` — all pass.

### Inner loop 2: port `sketches/fence-torn-paper/__init__.py`

**Manual verification (after implementation):** Open `http://localhost:8000/sketch/fence-torn-paper`. Confirm the edge-detected output renders. Change the `color` param — verify edge color updates live.

**Implementation:**

Rewrite `sketches/fence-torn-paper/__init__.py`:

```python
"""Fence Torn Paper — Canny edge detection on a weathered fence with torn paper."""

from __future__ import annotations

from typing import Annotated

import cv2
import numpy as np
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step

from sketches import SITE_BUNDLE
from sketches.types import Color, Image


@sketch(date="2026-03-29")
def fence_torn_paper() -> None:
    """weathered fence with torn paper and emphasized edges."""
    photo = source(
        "assets/fence-torn-paper.png",
        lambda p: Image(cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)),
    )
    blurred = gaussian_blur(photo)
    edges = canny_edge(blurred)
    result = canny_composite(photo, edges)
    output(result, SITE_BUNDLE)


@step
def gaussian_blur(
    image: Image,
    *,
    kernel: Annotated[int, Param(min=1, max=31, step=2, debounce=150)] = 5,
    sigma: Annotated[float, Param(min=0.0, max=10.0, step=0.1, debounce=150)] = 1.4,
) -> Image:
    """Return the Gaussian-blurred image."""
    k = kernel if kernel % 2 == 1 else kernel + 1
    return Image(cv2.GaussianBlur(image.array, (k, k), sigma))


@step
def canny_edge(
    image: Image,
    *,
    low: Annotated[int, Param(min=0, max=500, step=1, debounce=150)] = 50,
    high: Annotated[int, Param(min=0, max=500, step=1, debounce=150)] = 150,
) -> Image:
    """Return the Canny edge mask as a single-channel image."""
    src = image.array
    gray = cv2.cvtColor(src, cv2.COLOR_RGB2GRAY) if src.ndim == 3 else src
    return Image(cv2.Canny(gray, low, high))


@step
def canny_composite(
    source_img: Image,
    edges: Image,
    *,
    weight: Annotated[int, Param(min=1, max=21, step=2, debounce=150)] = 1,
    color: Annotated[Color, Param(debounce=150)] = Color("#ff69b4"),
) -> Image:
    """Return source image with colored edges composited on top."""
    src = source_img.array
    mask = edges.array
    if weight > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (weight, weight))
        mask = cv2.dilate(mask, kernel)
    color_layer = np.full_like(src, (color.r, color.g, color.b), dtype=np.uint8)
    edge_mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    result = np.where(edge_mask_3ch > 0, color_layer, src)
    return Image(result.astype(np.uint8))
```

Notes:

- `Color` is now imported from `sketches.types`.
- The step parameter `source` was renamed to `source_img` to avoid shadowing the `source()` function.
- `Postprocess` deleted. `Image.to_bytes(mode)` handles compression.
- No `presets=` filter on `output()` — `fence-torn-paper` has only one preset (`default`) and no filter means "all presets."

**Preset migration:**

`default.json` — rename keys:

- `gaussian_blur_0` → `gaussian_blur`
- `canny_edge_0` → `canny_edge`
- `canny_composite_0` → `canny_composite`

**After this loop:** `Color` in `core/params.py` is still needed by `sketchbook.core.presets._Encoder`. The `_Encoder` class serializes `Color` to its hex string. Since `Color` is now in `sketches.types`, update the import in `core/presets.py`:

```python
# Before
from sketchbook.core.params import Color

# After
try:
    from sketches.types import Color as _Color  # userland
except ImportError:
    _Color = None  # type: ignore[assignment,misc]
```

Wait — this violates the hard rule: **framework must never import from sketches**. The `_Encoder` class in `core/presets.py` must be decoupled from `Color`.

**Correct approach:** Make `_Encoder.default` duck-type instead of `isinstance(o, Color)`:

```python
class _Encoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if hasattr(o, "to_tweakpane"):
            return o.to_tweakpane()
        return super().default(o)
```

`Color.to_tweakpane()` returns the hex string — exactly what we want to serialize. This removes the framework's dependency on `Color` entirely and works for any rich type that knows how to serialize itself.

**Checkpoint:** Prompt for manual verification — open `http://localhost:8000/sketch/fence-torn-paper` and confirm before proceeding.

---

### Inner loop 3: port `sketches/cardboard/__init__.py`

**Manual verification (after implementation):** Start `mise run sketches:dev`, open `http://localhost:8000/sketch/cardboard`, and confirm the circle grid output renders. Drag the `count` and `radius` sliders and verify the output updates live.

**Implementation:**

Rewrite `sketches/cardboard/__init__.py`:

```python
"""Cardboard — greyscale cardboard texture with a grid of inverted circles."""

from __future__ import annotations

from typing import Annotated, Any

import cv2
import numpy as np
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step

from sketches import SITE_BUNDLE
from sketches.types import Image


@sketch(date="2026-03-09")
def cardboard() -> None:
    """greyscale cardboard texture with a grid of inverted circles."""
    img = source("assets/cardboard.jpg", Image.load)
    mask = circle_grid_mask(img)
    result = difference_blend(img, mask)
    output(result, SITE_BUNDLE, presets=["nine"])


@step
def circle_grid_mask(
    image: Image,
    *,
    count: Annotated[int, Param(min=1, max=20, step=1, debounce=150)] = 3,
    radius: Annotated[float, Param(min=0.0, max=1.0, step=0.01, debounce=150)] = 0.75,
) -> Image:
    """Draw a uniform grid of filled white circles on a black background."""
    src = image.array
    h, w = src.shape[:2]
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    cell_w = w / count
    cell_h = h / count
    for row in range(count):
        for col in range(count):
            cx = int((col + 0.5) * cell_w)
            cy = int((row + 0.5) * cell_h)
            r = int(min(cell_w, cell_h) * radius / 2)
            cv2.circle(canvas, (cx, cy), r, (255, 255, 255), thickness=-1)
    return Image(canvas)


@step
def difference_blend(image: Image, mask: Image) -> Image:
    """Return the per-pixel absolute difference of image and mask."""
    return Image(cv2.absdiff(image.array, mask.array))
```

Notes:

- `Postprocess` is deleted — `Image.to_bytes(mode)` handles quality.
- Step IDs become `circle_grid_mask` and `difference_blend` (no `_0` suffix).
- The old `Cardboard` class is removed.

**Preset migration:**

`cardboard/presets/nine.json` currently has key `circle_grid_mask_0`. Rename to `circle_grid_mask`:

```json
{
  "circle_grid_mask": {
    "count": 3,
    "radius": 0.75
  }
}
```

Update `_active.json` keys to match.

**Checkpoint:** Prompt for manual verification — open `http://localhost:8000/sketch/cardboard` and confirm the output renders before proceeding.

---

### Inner loop 4: port `sketches/cardboard_stripes/__init__.py`

**Manual verification (after implementation):** Open `http://localhost:8000/sketch/cardboard-stripes`. Confirm the striped output renders. Adjust `count`, `vert_margin`, and `width_fn` — verify live updates.

**Implementation:**

Rewrite `sketches/cardboard_stripes/__init__.py`:

```python
"""Cardboard Stripes — cardboard texture with DIFFERENCE-blended horizontal stripes."""

from __future__ import annotations

import math
from typing import Annotated, Any

import cv2
import numpy as np
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, sketch, step

from sketches import SITE_BUNDLE
from sketches.types import Image


_WIDTH_FNS: dict[str, Any] = {
    "uniform": lambda i, n: 1.0,
    "linear": lambda i, n: i / (n - 1) if n > 1 else 1.0,
    "exponential": lambda i, n: (math.exp(i / (n - 1)) - 1) / (math.e - 1) if n > 1 else 1.0,
    "sinusoidal": lambda i, n: math.sin(math.pi * i / (n - 1)) if n > 1 else 1.0,
}

_WIDTH_FN_OPTIONS = list(_WIDTH_FNS.keys())
_ALIGN_OPTIONS = ["left", "center", "right"]


@sketch(date="2026-03-12")
def cardboard_stripes() -> None:
    """greyscale cardboard texture with a stack of inverted horizontal bars."""
    img = source("assets/cardboard.jpg", Image.load)
    mask = stripes_mask(img)
    result = difference_blend(img, mask)
    output(result, SITE_BUNDLE, presets=["three", "steps"])


@step
def stripes_mask(
    image: Image,
    *,
    count: Annotated[int, Param(min=1, max=50, step=1, debounce=150)] = 3,
    vert_margin: Annotated[float, Param(min=0.0, max=1.0, step=0.01, debounce=150)] = 0.45,
    horz_margin: Annotated[float, Param(min=0.0, max=1.0, step=0.01, debounce=150)] = 0.2,
    width_fn: Annotated[str, Param(options=_WIDTH_FN_OPTIONS)] = "uniform",
    invert_fn: bool = False,
    align: Annotated[str, Param(options=_ALIGN_OPTIONS)] = "center",
) -> Image:
    """Draw horizontal white rectangles on a black canvas with the configured layout."""
    src = image.array
    h, w = src.shape[:2]
    inset = horz_margin * 0.5 * w
    available_w = w - 2 * inset
    total_gap = vert_margin * h
    gap = total_gap / (count + 1)
    rect_h = (h - total_gap) / count
    fn = _WIDTH_FNS[width_fn]
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    for i in range(count):
        raw = fn(i, count)
        v = (1.0 - raw) if invert_fn else raw
        rect_w = available_w * _lerp(v, 1.0 / count, 1.0)
        if align == "left":
            x = inset
        elif align == "right":
            x = inset + available_w - rect_w
        else:
            x = inset + (available_w - rect_w) / 2
        y = gap + i * (rect_h + gap)
        cv2.rectangle(canvas, (int(x), int(y)), (int(x + rect_w), int(y + rect_h)), (255, 255, 255), thickness=-1)
    return Image(canvas)


@step
def difference_blend(image: Image, mask: Image) -> Image:
    """Return the per-pixel absolute difference of image and mask."""
    img = image.array
    msk = mask.array
    if img.shape != msk.shape:
        msk = cv2.resize(msk, (img.shape[1], img.shape[0]))
    return Image(cv2.absdiff(img, msk))


def _lerp(t: float, a: float, b: float) -> float:
    """Linearly interpolate between a and b by t."""
    return a + t * (b - a)
```

Notes:

- `DifferenceBlend` is intentionally duplicated from `cardboard` — no shared abstraction yet.
- `Postprocess` deleted.
- `invert_fn: bool` has no `Param` annotation (it's just a plain bool input). This is fine — `extract_params` will not pick it up as a param. **Decision needed:** does it need `Param` to appear in the Tweakpane UI? Looking at the old sketch: `add_param("invert_fn", bool, default=False)` — yes, it should be tunable. Add `Annotated[bool, Param()]` annotation.

**Preset migration:**

Rename keys in `three.json` and `steps.json`: `stripes_mask_0` → `stripes_mask`.

**Checkpoint:** Prompt for manual verification — open `http://localhost:8000/sketch/cardboard-stripes` and confirm before proceeding.

---

### Inner loop 5: port `sketches/kick-polygons/__init__.py`

**Manual verification (after implementation):** Open `http://localhost:8000/sketch/kick-polygons`. Confirm the radial arrangement renders. Change `n` — verify copy count updates live. Load the `dress-star` preset.

**Implementation:**

Rewrite `sketches/kick-polygons/__init__.py` — note the module name uses a hyphen, so the Python module attribute access uses `sketches.kick_polygons` (underscored by Python's import). The file path is `sketches/kick-polygons/__init__.py`.

```python
"""Kick polygons — radial arrangement of she-kick image copies around a center origin."""

from __future__ import annotations

from typing import Annotated

import cv2
import numpy as np
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, SketchContext, sketch, step

from sketches import SITE_BUNDLE
from sketches.types import Image


@sketch(date="2026-04-11")
def kick_polygons() -> None:
    """radial arrangement of image copies forming polygon patterns."""
    photo = source(
        "assets/she-kick.png",
        lambda p: Image(cv2.imread(str(p), cv2.IMREAD_UNCHANGED)),
    )
    scale = downscale_factor()
    thumb = downscale(photo, scale)
    result = radial_arrange(thumb)
    output(result, SITE_BUNDLE, presets=["dress-star", "fist-pinwheel", "sun-pinwheel", "thirteen-fist-fin"])


@step
def downscale_factor(ctx: SketchContext) -> float:
    """Return 0.25 in dev mode, 0.5 in build mode."""
    return 0.25 if ctx.mode == "dev" else 0.5


@step
def downscale(image: Image, scale: float) -> Image:
    """Return the image scaled by scale factor using area interpolation."""
    src = image.array
    h, w = src.shape[:2]
    result = cv2.resize(
        src,
        (max(1, int(w * scale)), max(1, int(h * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return Image(result)


@step
def radial_arrange(
    image: Image,
    *,
    n: Annotated[int, Param(min=0, max=16, step=1, debounce=150)] = 6,
    offset: Annotated[float, Param(min=-180.0, max=180.0, step=1.0, debounce=150)] = 0.0,
    s_rotation: Annotated[float, Param(min=-180.0, max=180.0, step=1.0, debounce=150)] = 0.0,
    s_radial: Annotated[float, Param(min=-2.0, max=2.0, step=0.05, debounce=150)] = 0.0,
    s_flip_h: Annotated[bool, Param()] = False,
    s_flip_v: Annotated[bool, Param()] = False,
) -> Image:
    """Place n copies of an image radiating outward from the center origin."""
    # ... (body copied verbatim from RadialArrange.process, replacing inputs["image"].data
    # with image.array)
    ...
```

Note: Old `Downscale(scale)` was constructed at build time with `scale=0.25` (dev) or `scale=0.5` (build). The new `downscale_factor` step injects `SketchContext` and returns the appropriate value. `s_radial.step` changes from `0.01` (old) to `0.05` (matching old `add_param` call in `RadialArrange.setup`).

**Preset migration:**

All kick-polygons presets have key `radial_arrange_0`. Rename to `radial_arrange` in all six files: `dress-star.json`, `fist-pinwheel.json`, `sun-pinwheel.json`, `thirteen-fist-fin.json`, `nine-spike.json`, `trefoil.json`.

**Checkpoint:** Prompt for manual verification — open `http://localhost:8000/sketch/kick-polygons` and confirm before proceeding.

---

### Inner loop 6: drop the `/v3` route prefix (flag day)

**Failing unit test (`tests/unit/test_v3_routes_no_prefix.py`):**

```python
from fastapi.testclient import TestClient

def test_sketch_route_at_root(fn_registry_client):
    """After the prefix drop, /sketch/{id} hits the v3 route, not the old one."""
    response = fn_registry_client.get("/sketch/cardboard_v3")
    assert response.status_code == 200

def test_no_v3_prefix_route(fn_registry_client):
    response = fn_registry_client.get("/v3/sketch/cardboard_v3")
    assert response.status_code == 404
```

**Implementation:**

1. In `server/routes/v3.py`:
   - Change `router = APIRouter(prefix="/v3")` → `router = APIRouter()`
   - Update every hardcoded `/v3/workdir/...` URL string to `/workdir/...`
   - Update every hardcoded `/v3/ws/...` to `/ws/...`
   - Update `"url_prefix": "/v3"` template context to `"url_prefix": ""`

2. In `server/app.py`:
   - Replace all old router includes (sketch, params, presets, ws, dag) with only `v3_routes.router`.
   - Remove the `SketchRegistry` entirely — `create_app` now only takes `fn_registry`.
   - Remove `candidates` and `sketches` parameters.
   - Remove `StaticFiles` workdir mounts for old sketches (the v3 router handles workdir via `FileResponse`).
   - Update the lifespan to only start/stop `fn_registry`'s watcher.

3. In `server/routes/sketch.py`'s index handler: since old routes are deleted, the index view is now in `v3.py`. Add a `GET /` index route to `v3.py` that lists all v3 sketches.

4. In `server/_dev.py`: remove `discover_sketches` / `candidates` / `SketchRegistry` — only `discover_sketch_fns` + `SketchFnRegistry`.

5. In `discovery.py`: `discover_sketches` can stay (it's not imported from sketches) but remove import of `Sketch` from `core/sketch.py` if that file is being deleted. Actually, defer deletion of `discovery.py`'s `discover_sketches` until step 7.

**Checkpoint:** `uv run pytest tests/unit/test_v3_routes_no_prefix.py` — all pass. Also verify old route unit tests now fail (they will be deleted in loop 7).

---

### Inner loop 7: delete old framework code and old tests

No new unit test for this loop — the acceptance test `test_no_old_framework_symbols` is the check.

**Files to delete:**

```
framework/src/sketchbook/core/sketch.py
framework/src/sketchbook/core/step.py
framework/src/sketchbook/core/dag.py
framework/src/sketchbook/core/types.py
framework/src/sketchbook/steps/source.py
framework/src/sketchbook/steps/output_bundle.py
framework/src/sketchbook/steps/site_output.py
framework/src/sketchbook/steps/__init__.py
framework/src/sketchbook/server/routes/sketch.py
framework/src/sketchbook/server/routes/params.py
framework/src/sketchbook/server/routes/presets.py
framework/src/sketchbook/server/routes/ws.py
framework/src/sketchbook/server/routes/dag.py
framework/src/sketchbook/server/registry.py
framework/src/sketchbook/server/deps.py
framework/src/sketchbook/server/tweakpane.py
```

**Files to trim:**

- `core/params.py` — delete `ParamDef`, `ParamRegistry`, `_coerce_bool`, `Color`. File becomes empty or contains only `_BOOL_TRUE_STRINGS`/`_BOOL_FALSE_STRINGS` if still needed. If nothing remains, delete the file.
- `core/executor.py` — delete (superseded by `executor_v3.py`). But check if anything still imports it.
- `core/presets.py` — delete `PresetManager`, `_snapshot_params` (old DAG version), keep only `_snapshot_params_built`, `load_active_into_built`, `save_active_from_built`, `load_preset_into_built`, `save_preset_from_built`, `list_preset_names`, `_Encoder`.
- `discovery.py` — remove `find_sketch_class`, `discover_sketches`; keep only `discover_sketch_fns`. Remove `from sketchbook.core.sketch import Sketch`.
- `server/app.py` — simplified to only create app with `fn_registry`.
- `__init__.py` (`framework/src/sketchbook/__init__.py`) — remove `from sketchbook.core.sketch import Sketch` if present.

**Old tests to delete:**

```
tests/unit/test_step.py
tests/unit/test_sketch.py
tests/unit/test_dag.py
tests/unit/test_types.py
tests/unit/test_source.py
tests/unit/test_params.py          (old ParamDef/ParamRegistry tests)
tests/unit/test_sketch_mode.py     (old Sketch.mode tests)
tests/unit/test_builder.py         (old build_bundle tests)
tests/unit/test_executor.py        (old execute() tests)
tests/unit/test_presets.py         (old PresetManager tests)
tests/acceptance/test_walking_skeleton.py
tests/acceptance/test_sketch_browser.py
tests/acceptance/test_sketch_mode.py
tests/acceptance/test_color_param.py
tests/acceptance/test_explicit_wiring.py
tests/acceptance/test_hotreload.py
tests/acceptance/test_loader_decoupling.py
tests/acceptance/test_parallel_variants.py
tests/acceptance/test_preset_persistence.py
tests/acceptance/test_real_step.py
tests/acceptance/test_static_site.py
tests/acceptance/test_dag_overview.py
tests/steps.py
```

**Checkpoint:** `uv run pytest tests/acceptance/test_cutover.py` — the `test_no_old_framework_symbols` test passes.

---

### Outer loop check: run the full acceptance test

```
uv run pytest tests/acceptance/test_cutover.py -v
```

All three tests must pass:

1. `test_no_old_framework_symbols` — no `PipelineStep`, `from sketchbook.core.sketch`, or `DAGNode` in any framework `.py`
2. `test_all_sketches_load_in_dev_server` — `GET /sketch/{slug}` returns 200 for all four slugs
3. `test_build_produces_valid_site` — `manifest.json` contains all four sketches

Then run the full suite:

```
uv run pytest
```

All v3 tests still pass. Old test files were deleted.

---

## Files to create

| File | Description |
|---|---|
| `tests/acceptance/test_cutover.py` | Acceptance test (full spec below) |
| `tests/unit/test_types_v3.py` | Unit tests for `Color` in `sketches/types.py` |
| `tests/unit/test_v3_routes_no_prefix.py` | Route-prefix drop verification |

## Files to modify

| File | Description |
|---|---|
| `sketches/types.py` | Add `Color` class (copied from `core/params.py`) |
| `sketches/cardboard/__init__.py` | Full rewrite: `@step` functions + `@sketch` |
| `sketches/cardboard_stripes/__init__.py` | Full rewrite: `@step` functions + `@sketch` |
| `sketches/fence-torn-paper/__init__.py` | Full rewrite: `@step` functions + `@sketch` |
| `sketches/kick-polygons/__init__.py` | Full rewrite: `@step` functions + `@sketch` |
| `sketches/cardboard/presets/nine.json` | Rename key `circle_grid_mask_0` → `circle_grid_mask` |
| `sketches/cardboard/presets/_active.json` | Update step IDs |
| `sketches/cardboard_stripes/presets/three.json` | Rename key `stripes_mask_0` → `stripes_mask` |
| `sketches/cardboard_stripes/presets/steps.json` | Rename key `stripes_mask_0` → `stripes_mask` |
| `sketches/cardboard_stripes/presets/_active.json` | Update step IDs |
| `sketches/fence-torn-paper/presets/default.json` | Rename all three step-ID keys |
| `sketches/fence-torn-paper/presets/_active.json` | Update step IDs |
| `sketches/kick-polygons/presets/*.json` (all 6 named) | Rename key `radial_arrange_0` → `radial_arrange` |
| `sketches/kick-polygons/presets/_active.json` | Update step IDs |
| `core/presets.py` | Remove `Color` import; make `_Encoder` duck-type via `to_tweakpane()`; delete old `PresetManager` and `_snapshot_params` |
| `core/params.py` | Delete `Color`, `ParamDef`, `ParamRegistry`, `_coerce_bool`; delete file if empty |
| `core/executor.py` | Delete file |
| `discovery.py` | Delete `find_sketch_class`, `discover_sketches`; remove `Sketch` import |
| `server/routes/v3.py` | Drop `/v3` prefix; add `GET /` index; update all URL strings |
| `server/app.py` | Remove old registry/routes; simplify to fn_registry only |
| `server/_dev.py` | Remove `discover_sketches` / `candidates` path |
| `server/__init__.py` | Remove any `Sketch` re-exports |

## Files to delete

| File | Reason |
|---|---|
| `core/sketch.py` | Superseded by `@sketch` decorator |
| `core/step.py` | Superseded by `@step` decorator |
| `core/dag.py` | Superseded by `BuiltDAG` |
| `core/types.py` | `Image` moved to `sketches/types.py` |
| `steps/source.py` | Superseded by `source()` function |
| `steps/output_bundle.py` | Superseded by `output()` function |
| `steps/site_output.py` | Unused in v3 |
| `steps/__init__.py` | Directory will be empty |
| `server/routes/sketch.py` | Old-API sketch routes |
| `server/routes/params.py` | Old-API param routes |
| `server/routes/presets.py` | Old-API preset routes |
| `server/routes/ws.py` | Old-API WebSocket route |
| `server/routes/dag.py` | Old-API DAG overview route |
| `server/registry.py` | `SketchRegistry` superseded by `SketchFnRegistry` |
| `server/deps.py` | FastAPI deps for old registry |
| `server/tweakpane.py` | Old Tweakpane adapter; superseded by `tweakpane_v3.py` |
| `tests/unit/test_step.py` | Superseded by `test_decorators.py` |
| `tests/unit/test_sketch.py` | Superseded by `test_wiring.py` |
| `tests/unit/test_dag.py` | Superseded by `test_building_dag.py` |
| `tests/unit/test_types.py` | `Image` in `sketches/types.py` is userland |
| `tests/unit/test_source.py` | `SourceFile` gone |
| `tests/unit/test_params.py` | Old `ParamDef`/`ParamRegistry` tests |
| `tests/unit/test_sketch_mode.py` | Old `Sketch.mode` tests |
| `tests/unit/test_builder.py` | Old `build_bundle` tests |
| `tests/unit/test_executor.py` | Old `execute()` tests |
| `tests/unit/test_presets.py` | Old `PresetManager` tests |
| `tests/acceptance/test_walking_skeleton.py` | Old-API skeleton |
| `tests/acceptance/test_sketch_browser.py` | Old-API browser test |
| `tests/acceptance/test_sketch_mode.py` | Old-API mode test |
| `tests/acceptance/test_color_param.py` | Old-API Color test |
| `tests/acceptance/test_explicit_wiring.py` | Old-API wiring test |
| `tests/acceptance/test_hotreload.py` | Old-API hot-reload test |
| `tests/acceptance/test_loader_decoupling.py` | Old-API loader test |
| `tests/acceptance/test_parallel_variants.py` | Old `build_bundle` test |
| `tests/acceptance/test_preset_persistence.py` | Old-API preset test |
| `tests/acceptance/test_real_step.py` | Old-API step test |
| `tests/acceptance/test_static_site.py` | Old `build_bundle` site test |
| `tests/acceptance/test_dag_overview.py` | Old-API DAG overview test |
| `tests/steps.py` | Old test step helpers |

---

## Acceptance test (full spec)

```python
# tests/acceptance/test_cutover.py

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sketchbook.bundle.builder import build_bundle_fns
from sketchbook.discovery import discover_sketch_fns

_FRAMEWORK_SRC = Path("framework/src/sketchbook")
_SKETCHES_DIR = Path("sketches")

_FORBIDDEN_SYMBOLS = {
    "PipelineStep",
    "from sketchbook.core.sketch",
    "DAGNode",
    "DAG(",
    "class DAG",
}


def test_no_old_framework_symbols():
    """The framework source contains no references to old API symbols."""
    violations: list[str] = []
    for py_file in _FRAMEWORK_SRC.rglob("*.py"):
        text = py_file.read_text()
        for term in _FORBIDDEN_SYMBOLS:
            if term in text:
                violations.append(f"{py_file}: found '{term}'")
    assert not violations, "\n".join(violations)


def test_all_sketches_load_in_dev_server(fn_registry_client_real):
    """All four real sketches wire and serve without error via the root-prefixed routes."""
    for slug in ["cardboard", "cardboard-stripes", "fence-torn-paper", "kick-polygons"]:
        response = fn_registry_client_real.get(f"/sketch/{slug}")
        assert response.status_code == 200, f"Sketch '{slug}' failed: {response.text}"


def test_build_produces_valid_site(tmp_path):
    """build_bundle_fns discovers all four ported sketches and writes a valid manifest."""
    sketch_fns = discover_sketch_fns(_SKETCHES_DIR)
    assert len(sketch_fns) >= 4, f"Expected >= 4 sketch functions, got: {list(sketch_fns)}"

    build_bundle_fns(sketch_fns, _SKETCHES_DIR, tmp_path, "bundle", workers=1)

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    slugs = {e["slug"] for e in manifest}
    assert "cardboard" in slugs
    assert "cardboard-stripes" in slugs
    assert "kick-polygons" in slugs
```

The `fn_registry_client_real` fixture wires a `SketchFnRegistry` against the actual `sketches/` directory (with real asset files available). It must be added to `conftest.py`:

```python
@pytest.fixture
def fn_registry_client_real():
    """TestClient wired to a real SketchFnRegistry against the actual sketches/ directory."""
    from sketchbook.discovery import discover_sketch_fns
    from sketchbook.server.app import create_app
    from sketchbook.server.fn_registry import SketchFnRegistry

    sketches_dir = Path(__file__).parent.parent.parent / "sketches"
    sketch_fns = discover_sketch_fns(sketches_dir)
    fn_registry = SketchFnRegistry(sketch_fns, sketches_dir=sketches_dir)
    app = create_app(fn_registry=fn_registry)
    return TestClient(app)
```

Note: `test_build_produces_valid_site` requires actual sketch asset files on disk to execute successfully. In CI without assets this test should be marked `@pytest.mark.skipif(not asset_available, ...)` or run only locally. For now, mark it with a docstring note.

---

## Prior art

| File | Role | Notes |
|---|---|---|
| `sketches/cardboard_v3/__init__.py` | Direct model | The complete v3 pattern to replicate in each sketch port: `@step` for each processing function, `@sketch` for the entry point, `Image` from `sketches.types`, `source`/`output` from `core.building_dag` |
| `core/params.py` (`Color`) | Port source | `Color.__init__`, `__str__`, `to_bgr`, `to_tweakpane` copy verbatim to `sketches/types.py` |
| `core/presets.py` (`_Encoder`) | Modify | Change `isinstance(o, Color)` check to `hasattr(o, "to_tweakpane")` duck-type |
| `server/routes/v3.py` | Modify | Drop `prefix="/v3"`, add index route, update URL strings |
| `tests/acceptance/test_static_site_v3.py` | Reference | Pattern for `build_bundle_fns` assertion in `test_build_produces_valid_site` |
| `tests/conftest.py` | Modify | Add `fn_registry_client_real` fixture |

---

## Definition of done

### Acceptance test

- [ ] `tests/acceptance/test_cutover.py::test_no_old_framework_symbols` passes
- [ ] `tests/acceptance/test_cutover.py::test_all_sketches_load_in_dev_server` passes (requires assets)
- [ ] `tests/acceptance/test_cutover.py::test_build_produces_valid_site` passes (requires assets)

### Sketch ports

- [ ] `sketches/cardboard/__init__.py` ported to `@step`/`@sketch`; `Cardboard`, `Postprocess` deleted
- [ ] `sketches/cardboard_stripes/__init__.py` ported; `CardboardStripes`, `Postprocess` deleted
- [ ] `sketches/fence-torn-paper/__init__.py` ported; `FenceTornPaper`, `Postprocess` deleted; `Color` imported from `sketches.types`
- [ ] `sketches/kick-polygons/__init__.py` ported; `KickPolygons`, `Downscale(scale)`, `Postprocess` deleted; `downscale_factor(ctx)` step added

### Preset migration

- [ ] `cardboard/presets/nine.json` — key renamed to `circle_grid_mask`
- [ ] `cardboard_stripes/presets/three.json` and `steps.json` — key renamed to `stripes_mask`
- [ ] `fence-torn-paper/presets/default.json` — all three keys renamed
- [ ] `kick-polygons/presets/*.json` (6 files) — key renamed to `radial_arrange`
- [ ] All `_active.json` files updated to match new step IDs

### `sketches/types.py`

- [ ] `Color` class present with `__init__`, `__str__`, `to_bgr`, `to_tweakpane`
- [ ] `tests/unit/test_types_v3.py` passes

### Route prefix

- [ ] `server/routes/v3.py` serves all routes at root (no `/v3` prefix)
- [ ] `GET /sketch/{id}` returns 200 for v3 sketches
- [ ] `GET /v3/sketch/{id}` returns 404 (prefix gone)
- [ ] WebSocket at `/ws/{id}` (not `/v3/ws/{id}`)
- [ ] Workdir files at `/workdir/{id}/{file}` (not `/v3/workdir/...`)
- [ ] Index `GET /` lists all v3 sketches

### Old code deleted

- [ ] `core/sketch.py` deleted
- [ ] `core/step.py` deleted
- [ ] `core/dag.py` deleted
- [ ] `core/types.py` deleted
- [ ] `steps/` directory deleted
- [ ] `server/routes/sketch.py`, `params.py`, `presets.py`, `ws.py`, `dag.py` deleted
- [ ] `server/registry.py` deleted
- [ ] `server/deps.py` deleted
- [ ] `server/tweakpane.py` deleted
- [ ] `core/params.py` trimmed or deleted (no `Color`, `ParamDef`, `ParamRegistry`)
- [ ] `core/executor.py` deleted
- [ ] Old test files listed above deleted

### Surviving v3 tests still pass

- [ ] `tests/acceptance/test_walking_skeleton_v3.py`
- [ ] `tests/acceptance/test_params_v3.py`
- [ ] `tests/acceptance/test_presets_v3.py`
- [ ] `tests/acceptance/test_static_site_v3.py`
- [ ] `tests/unit/test_decorators.py`
- [ ] `tests/unit/test_building_dag.py`
- [ ] `tests/unit/test_introspect.py`
- [ ] `tests/unit/test_wiring.py`
- [ ] `tests/unit/test_executor_v3.py`
- [ ] `tests/unit/test_protocol.py`
- [ ] `tests/unit/test_tweakpane_v3.py`
- [ ] `tests/unit/test_builder_v3.py`
- [ ] `tests/unit/test_presets_v3.py`
- [ ] `tests/unit/test_params_v3.py`
- [ ] `tests/unit/test_discovery.py`
- [ ] `tests/unit/test_fn_registry_v3_presets.py`
- [ ] `tests/unit/test_v3_routes_params.py`
- [ ] `tests/unit/test_v3_routes_presets.py`

### Cleanup

- [ ] Zero imports of `PipelineStep`, `Sketch`, `DAGNode`, `DAG` anywhere in `framework/`
- [ ] Zero imports from `sketches.*` anywhere in `framework/`
- [ ] `mise run lint` passes with zero violations

---

## Manual verification

After all automated checks pass:

1. Ensure sketch assets are present on disk:
   - `sketches/cardboard/assets/cardboard.jpg` (symlink to shared library)
   - `sketches/cardboard_stripes/assets/cardboard.jpg`
   - `sketches/fence-torn-paper/assets/fence-torn-paper.png`
   - `sketches/kick-polygons/assets/she-kick.png`

2. Start the dev server:

   ```
   mise run sketches:dev
   ```

3. Open `http://localhost:8000/` — verify the index lists all four sketches (no `/v3/` in URLs).

4. Open each sketch and confirm the output image renders:
   - `http://localhost:8000/sketch/cardboard`
   - `http://localhost:8000/sketch/cardboard-stripes`
   - `http://localhost:8000/sketch/fence-torn-paper`
   - `http://localhost:8000/sketch/kick-polygons`

5. For `cardboard`: drag the `count` slider — the circle grid updates live.
   For `fence-torn-paper`: change the `color` param — edge color updates.
   For `kick-polygons`: change `n` — number of radial copies updates.

6. For `cardboard`: load the `nine` preset — params snap to saved values.
   For `kick-polygons`: load the `dress-star` preset.

7. Check WebSocket URL in browser DevTools Network tab — confirm it connects to `ws://localhost:8000/ws/cardboard` (no `/v3/` prefix).

8. Run the build:

   ```
   uv run build
   ```

   Verify `sketches/bundle/manifest.json` exists and contains entries for `cardboard`, `cardboard-stripes`, `fence-torn-paper`, `kick-polygons`.

9. Commit any sketch changes — the four ported sketches and their migrated presets are kept.
