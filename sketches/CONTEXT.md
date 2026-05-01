# Sketches Context

`sketches/` is the userland half of Sketchbook. Each subdirectory is a self-contained creative module (a sketch). Shared types and steps live at the top level of this directory.

The framework knows nothing about this directory. Sketches depend on the framework; the framework never depends on sketches.

## Domain vocabulary

**Sketch** — a `@sketch`-decorated function in `sketches/<slug>/__init__.py` that wires a concrete pipeline. See framework `CONTEXT.md` for the mechanics.

**Image** — the shared userland value type for raster data. Backed by a NumPy array (OpenCV convention: BGR channel order). Satisfies `SketchValueProtocol`. Defined in `sketches/types.py`.

**Color** — a userland value type for an RGB color backed by a `#rrggbb` hex string. Satisfies `SketchValueProtocol` via Tweakpane's native color picker. Defined in `sketches/types.py`.

**BoundingBox** — a normalized spatial region `(x1, y1, x2, y2)` where all values are in `[0.0, 1.0]` relative to image dimensions. Defined in `sketches/types.py`. Used as pipeline data flowing between segmentation steps. Normalised coordinates remain valid when the source image is swapped for a higher-resolution version.

**Segmentation mask** — a single-channel (grayscale) `Image` where pixel values are 0 (background) or 255 (foreground). The canonical output of `sam_segment`. Kept separate from the source image so downstream steps can decide how to composite.

**Segmentation primitive** — a step whose sole job is to produce a segmentation mask. It has no opinion on how the mask is used. `sam_segment` is the only one today.

## Shared modules

**`sketches/types.py`** — value types shared across sketches: `Image`, `Color`, `BoundingBox`. A type lives here once it is used by more than one sketch, or when it is clearly general from the start.

**`sketches/steps.py`** — step functions shared across sketches. Steps live here when they are domain-generic (segmentation, geometric annotation) with no sketch-specific logic. A step starts here if it is clearly a primitive; otherwise it starts in a sketch and is promoted when a second sketch needs it.

## Segmentation pattern

Prompted image segmentation uses three steps wired in the sketch:

```
source image ──→ make_bbox ──→ annotate_bbox ──→ [preview output]
                    │
                    └──→ sam_segment ──→ [mask output]
source image ───────────────────────────↑
```

- `make_bbox` holds the four bbox params. It has no image input — it is a structured parameter source.
- `annotate_bbox` draws the rectangle on the source image. Cheap; provides instant visual feedback while tuning.
- `sam_segment` runs SAM2 inference. Receives the same `BoundingBox` from `make_bbox` — single source of truth. Returns a segmentation mask.

`BoundingBox` flows as pipeline data so that `annotate_bbox` and `sam_segment` share one set of params rather than duplicating them.

## SAM2 integration

SAM2 (Segment Anything Model 2, Meta) is accessed via HuggingFace `transformers`. Model weights are downloaded automatically on first use to `~/.cache/huggingface/`. Model size is a constant fixed per sketch — not a tunable param, because switching model sizes triggers a full reload.

`sam_segment` exposes a `mask_index` param (`0`–`2`, default `0`) to select among SAM2's three ranked mask candidates. The default picks the highest-confidence candidate; override when SAM2 misreads the subject.
