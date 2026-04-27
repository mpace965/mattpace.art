"""Preset persistence: _active.json load/save and named preset CRUD."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sketchbook.core.built_dag import BuiltDAG, BuiltNode

log = logging.getLogger("sketchbook.core.presets")


class _Encoder(json.JSONEncoder):
    """JSON encoder that serializes rich param types via to_tweakpane()."""

    def default(self, o: Any) -> Any:
        """Serialize any object that exposes to_tweakpane() as its wire form."""
        if hasattr(o, "to_tweakpane"):
            return o.to_tweakpane()
        return super().default(o)


def _apply_values(node: BuiltNode, values: dict[str, Any]) -> None:
    """Apply *values* to *node.param_values*, coercing each to its declared type."""
    from sketchbook.core.introspect import coerce_param

    spec_by_name = {s.name: s for s in node.param_schema}
    for param_name, value in values.items():
        if param_name not in node.param_values:
            continue
        spec = spec_by_name.get(param_name)
        node.param_values[param_name] = coerce_param(spec, value) if spec is not None else value


def _snapshot_params_built(dag: BuiltDAG) -> dict[str, Any]:
    """Return a mapping of step_id -> param values for all nodes with params."""
    data: dict[str, Any] = {}
    for node in dag.nodes_in_order():
        if node.param_values:
            data[node.step_id] = dict(node.param_values)
    return data


def load_active_into_built(dag: BuiltDAG, presets_dir: str | Path) -> tuple[bool, str | None]:
    """Read _active.json and apply values to BuiltNode.param_values.

    Return (dirty, based_on). No-op if file is missing.
    """
    active_path = Path(presets_dir) / "_active.json"
    if not active_path.exists():
        log.debug(f"No _active.json at {active_path}, using defaults")
        return False, None

    data: dict[str, Any] = json.loads(active_path.read_text())
    meta = data.get("_meta", {})
    dirty: bool = meta.get("dirty", False)
    based_on: str | None = meta.get("based_on")

    for step_id, values in data.items():
        if step_id == "_meta":
            continue
        node = dag.nodes.get(step_id)
        if node is None:
            log.warning(f"_active.json references unknown step '{step_id}', skipping")
            continue
        _apply_values(node, values)

    log.info(f"Loaded _active.json (dirty={dirty}, based_on={based_on!r})")
    return dirty, based_on


def save_active_from_built(
    dag: BuiltDAG,
    presets_dir: str | Path,
    dirty: bool,
    based_on: str | None,
) -> None:
    """Serialize BuiltNode.param_values to _active.json."""
    presets_dir = Path(presets_dir)
    presets_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "_meta": {
            "dirty": dirty,
            "based_on": based_on,
        },
        **_snapshot_params_built(dag),
    }
    (presets_dir / "_active.json").write_text(json.dumps(data, indent=2, cls=_Encoder))
    log.debug(f"Saved _active.json (dirty={dirty})")


def load_preset_into_built(dag: BuiltDAG, presets_dir: str | Path, name: str) -> None:
    """Read <name>.json and apply values to BuiltNode.param_values.

    Does not write to disk — caller handles _active.json.
    Raises FileNotFoundError if the preset file is missing.
    """
    preset_path = Path(presets_dir) / f"{name}.json"
    if not preset_path.exists():
        raise FileNotFoundError(f"Preset '{name}' not found at {preset_path}")
    data: dict[str, Any] = json.loads(preset_path.read_text())
    for step_id, values in data.items():
        if step_id == "_meta":
            continue
        node = dag.nodes.get(step_id)
        if node is None:
            log.warning(f"Preset '{name}' references unknown step '{step_id}', skipping")
            continue
        _apply_values(node, values)
    log.info(f"Loaded preset '{name}' into BuiltDAG")


def list_preset_names(presets_dir: str | Path) -> list[str]:
    """Return sorted list of named preset names from *presets_dir*.

    Excludes the ``_active`` sentinel file. Returns an empty list if the
    directory does not exist.
    """
    d = Path(presets_dir)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json") if p.stem != "_active")


def reset_to_defaults(dag: BuiltDAG) -> None:
    """Reset every node's param_values to the declared defaults."""
    for node in dag.nodes_in_order():
        for spec in node.param_schema:
            node.param_values[spec.name] = spec.default


def save_preset_from_built(dag: BuiltDAG, presets_dir: str | Path, name: str) -> None:
    """Snapshot current BuiltNode.param_values to <name>.json."""
    presets_dir = Path(presets_dir)
    presets_dir.mkdir(parents=True, exist_ok=True)
    snapshot = json.dumps(_snapshot_params_built(dag), indent=2, cls=_Encoder)
    (presets_dir / f"{name}.json").write_text(snapshot)
    log.info(f"Saved preset '{name}' from BuiltDAG")
