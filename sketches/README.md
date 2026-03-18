# Sketches

Each subdirectory is a self-contained sketch. Drop source assets into `assets/` and run the dev server to view it.

## DAG exercise sketches

The following sketches were created to exercise different DAG topologies before increment 5 implements proper branching/merging visualization. They run and execute correctly — the limitation is only in the left-panel renderer, which currently draws a simple sequential list rather than a true graph layout.

### `deep_blur`

```
source → blur_0 → blur_1 → blur_2 → edge_detect
```

Deep linear chain with three consecutive blur passes. Exercises repeated step type auto-naming (`gaussian_blur_0`, `gaussian_blur_1`, `gaussian_blur_2`) and deep topo sort.

Assets: `assets/photo.jpg`

### `fan_out`

```
source → blur
source → edge_detect
source → passthrough
```

Single source node with three independent downstream branches. Exercises a node referenced as `from_id` in multiple edges and a topo sort with one root and three leaves.

Assets: `assets/photo.jpg`

### `fan_in`

```
source_a → blur_a ─┐
                    ├─ blend
source_b → blur_b ─┘
```

Two independent sources merged by a single `Blend` step. Exercises `Sketch.add()` with a multi-key `inputs` dict (`image` and `overlay`) and the executor resolving both named inputs before calling `process()`.

Assets: `assets/photo_a.jpg`, `assets/photo_b.jpg`

### `diamond`

```
source → blur → edge_detect_0 ─┐
              ↘                  ├─ blend
               edge_detect_1 ──┘
```

Classic diamond: one shared intermediate node (`blur`) with two diverging branches that reconverge at `blend`. Exercises output caching on the shared node and topo ordering when in-degree > 1.

The two `EdgeDetect` instances are seeded with different threshold defaults (tight vs. loose) to produce visually distinct results before blending.

Assets: `assets/photo.jpg`

### `two_chains`

```
source_a → blur_a → edge_a

source_b → edge_b
```

Two fully disconnected subgraphs in one sketch. Exercises a topo sort over multiple connected components (two root nodes with no shared edges) and verifies both chains execute independently.

Assets: `assets/photo_a.jpg`, `assets/photo_b.jpg`

---

Proper branching/merging visualization is tracked under increment 5.
