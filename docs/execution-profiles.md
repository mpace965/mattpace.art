# Execution profiles

## Problem

Dev and build modes have different quality requirements — fast iteration wants small images and no compression; published output wants full resolution and compressed PNGs. There is no mechanism for this. Sketches currently hardcode `compress_level` in step code and manage draft scaling manually as sketch parameters, requiring hand-editing before every publish.

## Solution

Introduce `ExecutionProfile` — a frozen dataclass holding execution-quality values (`draft_scale: float`, `compress_level: int`). A `ProfileRegistry`, owned by the framework, holds named profiles with a cascade:

1. Sketch override for the active mode
2. Framework default for the active mode (warns if not found at sketch level)
3. Framework base — hard fails if missing

The base `Sketch` class gains a template method:

```python
def execution_profiles(self) -> dict[str, ExecutionProfile]:
    return {}
```

Sketches override it to layer in mode-specific values. The framework calls it once at construction and merges the result into the registry.

The execution context (`dev`, `build`) resolves the profile by mode name and passes it into `build(dag, profile)`. The sketch author wires values explicitly:

```python
def build(self, dag, profile):
    src = dag.add(Downscale(input, scale=profile.draft_scale))
    result = dag.add(MyStep(src))
    dag.add(OutputBundle(result, compress_level=profile.compress_level))
```

Nothing is implicit. Scaling and compression are opt-in and authored in `build()`.

## Definition of done

- [ ] `ExecutionProfile` frozen dataclass with `draft_scale` and `compress_level`
- [ ] `ProfileRegistry` with cascade lookup and appropriate warnings/failures
- [ ] Framework ships defaults: base, dev, build profiles
- [ ] `Sketch.execution_profiles()` template method; framework merges overrides at construction
- [ ] Execution context resolves and passes profile into `build()`
- [ ] `OutputBundle` accepts `compress_level` from the profile
- [ ] Unit tests cover cascade fallback, warning behaviour, and hard failure
- [ ] `mise run lint` passes
