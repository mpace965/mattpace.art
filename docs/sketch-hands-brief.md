# sketch: hands

## concept

Collage hands — scanned paper cutouts of hands in various positions and gestures — are placed along a path that emerges from following where they point. Each hand is a physical object with a texture and edge. Some point in one direction; some fork into two. The path meanders, branches, occasionally merges. The result is something between a map and a gesture notation, made from accumulated physical marks.

The hands are the grammar. The path is what they say.

## source material

Scan a tray of hand cutouts against a uniform background (white paper or black felt). Export the full scan. A Python/OpenCV step detects individual hand blobs via connected-component analysis (`cv2.connectedComponentsWithStats`) and crops each one to its own PNG with alpha. Assets live in `sketches/hands/assets/` as `hand_001.png`, `hand_002.png`, etc.

Each hand has a JSON sidecar (`hand_001.json`) with:

```json
{
  "anchor": [0.4, 0.8],
  "vectors": [
    {"angle_deg": 45,  "label": "primary"},
    {"angle_deg": 130, "label": "secondary"}
  ]
}
```

`anchor` is the fractional position of the wrist/entry point within the image bounding box — where the path arrives. `vectors` are outgoing directions. A hand with two vectors forks the path.

## annotation workflow

A bespoke OpenCV mouse-callback script (`sketches/hands/annotate.py`) opens each image in sequence. Click to place the anchor. Click-drag to draw each vector. Press `s` to write the sidecar and advance. Press `d` to delete the last vector. The script is a one-off tool, not a pipeline step.

> **deferred idea — in-browser annotation app:** A more general version of this could be an interactive p5.js app embedded in the dev server UI. The framework would support a new `to_html(url: str) -> str` method on output values (see framework increment below), and an `AnnotationApp` value type whose `to_html()` returns an iframe pointing to a static HTML+JS file served from `sketches/<slug>/apps/`. The app reads the input image and current annotation state via fetch, lets the user interact, and POSTs saves back. No `kind` field needed — rendering is entirely userland-owned. Waiting for a more compelling usecase before building this.

## path algorithm — hand-first

The path emerges from the hands rather than being planned in advance:

1. Place a hand at the starting position. Its `primary` vector gives a direction and distance to the next placement point.
2. At the new position, sample a hand from the collection whose incoming angle best matches the arrival direction (details under *sampling* below).
3. Place it. If it has a `secondary` vector, fork: push a new branch onto a queue with the secondary vector's direction and the current position.
4. Continue until the canvas is filled or a step count limit is reached.
5. Merge: when two active branches come within a threshold distance of each other, join them at their midpoint and continue as one.

The curve rendered through the anchor sequence is a Catmull-Rom spline — smooth, passes through the points, requires no manual tangent setting.

## sampling

Undecided. Candidates:

- **direction-matched random**: filter to hands within ±N degrees of arrival angle, pick uniformly from that subset
- **weighted by angular distance**: all hands eligible, weight by `exp(-k * Δangle)`, smooth falloff
- **no-repeat pool**: maintain a shuffle queue so no hand repeats until the pool is exhausted; combine with either of the above for directional preference

The choice affects whether the work reads as disciplined (tight angular filter) or loose and wandering (broad or weighted). Worth tuning as a parameter.

## pipeline shape

```
scan_ingest          ← full scan PNG → individual hand PNGs (one-time step, or external)
load_collection      ← reads hands/ dir, returns Collection[Hand]
build_path           ← hand-first walk, returns list of PlacedHand
composite            ← renders hands + spline onto canvas
output(result, ...)
```

`Hand` pairs an `Image` with its parsed `Annotation`. `PlacedHand` is a `Hand` plus a 2D transform (position, rotation to align with path tangent).

`Collection[T]` is a new userland-friendly wrapper discussed in the framework increment below.

## framework increments required

These are prerequisites, not part of the sketch itself. They belong in the framework and benefit all sketches.

### 1. rename `image_url` → `output_url`

Routes and WebSocket messages currently always emit a field called `image_url` regardless of what kind of value the step produces. Rename to `output_url` everywhere: `server/routes/sketches.py`, `server/fn_registry.py`, `server/templates/macros.html`, `server/templates/sketch.html`, `server/templates/step.html`.

Purely cosmetic but removes a misleading assumption from the API surface.

### 2. replace `kind` with `to_html()` — remove kind from the protocol

`kind` is a dispatch table that lives in the framework. Every new output type requires a framework change. The fix: move rendering decisions into the value.

Add `to_html(url: str) -> str` to `SketchValueProtocol` as a required (or defaulted) method. The server calls it and includes the result in the WebSocket `step_updated` message. The frontend does `element.innerHTML = msg.html`. No switch statement anywhere.

```python
class Image:
    def to_html(self, url: str) -> str:
        return f'<img src="{url}">'

class JSONValue:
    def to_html(self, url: str) -> str:
        return f'<pre data-src="{url}"></pre>'  # frontend fetches and pretty-prints

class Collection:
    def to_html(self, url: str) -> str:
        return f'<div class="gallery" data-src="{url}"></div>'  # frontend renders grid
```

`kind` is removed from `SketchValueProtocol`. `extension` already covers everything the executor and bundle builder need. Userland owns all rendering.

Migration: existing `Image` and `WandImage` implementations add `to_html()`; the `kind` attribute is dropped.

### 3. `Collection[T]` wrapper

A generic container for a sequence of values that implements `SketchValueProtocol`.

```python
class Collection[T]:
    extension = "json"
    items: list[T]

    def to_bytes(self, mode) -> bytes:
        # serialize as a manifest; individual items serialized separately by executor
        ...

    def to_html(self, url: str) -> str:
        return f'<div class="gallery" data-src="{url}"></div>'
```

The executor writes each item to `.workdir/{step_id}/{index}.{item.extension}` and the collection manifest to `.workdir/{step_id}.json`. A `source_dir()` convenience function produces a `Collection[T]` from a directory of files.

This lives in userland (`sketches/types.py`) initially. Promote to the framework if it proves generally useful.
