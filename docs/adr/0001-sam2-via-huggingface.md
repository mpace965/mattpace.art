# ADR 0001: use HuggingFace transformers for SAM2 integration

**Status:** accepted

## Context

SAM2 (Segment Anything Model 2) has two realistic integration paths:

1. **Meta's official `sam2` PyPI package** — purpose-built for SAM2. The prompted image prediction API is clean: `predictor.set_image(arr)` / `predictor.predict(box=...)`. Requires managing model weight files explicitly on disk.

2. **HuggingFace `transformers`** — `SamModel.from_pretrained("facebook/sam2-hiera-small")`. Downloads and caches weights automatically in `~/.cache/huggingface/`. The internal API is more verbose (separate processor object, triple-nested box format, explicit `post_process_masks` call), but all of that is hidden inside the step function.

## Decision

Use HuggingFace `transformers`.

The internal API verbosity is a one-time cost inside `sam_segment` — the pipeline interface (`sam_segment(image, box) -> Image`) is identical either way. The HuggingFace path buys automatic weight management and a consistent `from_pretrained` pattern that works for any model on the Hub. If future sketches want depth estimation, inpainting, or other models, they get the same caching and loading mechanism for free.

## Consequences

- Model weights live in `~/.cache/huggingface/`, not in a project-local `models/` directory.
- `transformers` and `torch` are added as sketch dependencies (heavy, but unavoidable for any deep learning inference).
- If a future step needs a model not on HuggingFace, this pattern does not apply — evaluate separately.
