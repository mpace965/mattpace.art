"""Preset persistence: _active.json load/save and named preset CRUD."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sketchbook.core.built_dag import BuiltDAG, BuiltNode
from sketchbook.core.dag import DAG

log = logging.getLogger("sketchbook.core.presets")


class _Encoder(json.JSONEncoder):
    """JSON encoder that serializes rich param types via to_tweakpane()."""

    def default(self, o: Any) -> Any:
        """Serialize any object that exposes to_tweakpane() as its wire form."""
        if hasattr(o, "to_tweakpane"):
            return o.to_tweakpane()
        return super().default(o)


def _snapshot_params(dag: DAG) -> dict[str, Any]:
    """Return a mapping of step_id -> param values for all nodes with params."""
    data: dict[str, Any] = {}
    for node in dag.topo_sort():
        values = node.step.param_values()
        if values:
            data[node.id] = values
    return data


class PresetManager:
    """Manages preset persistence for a sketch.

    All named presets and the active state live under presets_dir:
      <presets_dir>/_active.json   — current working state (dirty flag + based_on)
      <presets_dir>/<name>.json    — named preset snapshots

    The JSON format for named presets:
      { "<step_id>": { "<param>": <value>, ... }, ... }

    The format for _active.json wraps the same with _meta:
      { "_meta": { "dirty": bool, "based_on": str|null }, ... }
    """

    def __init__(self, presets_dir: str | Path) -> None:
        self._dir = Path(presets_dir)
        self._dirty: bool = False
        self._based_on: str | None = None

    @property
    def dirty(self) -> bool:
        """Return True if the active state has been edited since the last save/load."""
        return self._dirty

    @property
    def based_on(self) -> str | None:
        """Return the name of the preset that was last loaded, or None."""
        return self._based_on

    def mark_dirty(self) -> None:
        """Mark the active state as dirty (called after a param edit)."""
        self._dirty = True

    def load_active(self, dag: DAG) -> None:
        """Load _active.json into the DAG's step registries (no-op if missing)."""
        active_path = self._dir / "_active.json"
        if not active_path.exists():
            log.debug(f"No _active.json at {active_path}, using defaults")
            return

        data: dict[str, Any] = json.loads(active_path.read_text())
        meta = data.get("_meta", {})
        self._dirty = meta.get("dirty", False)
        self._based_on = meta.get("based_on")

        for step_id, values in data.items():
            if step_id == "_meta":
                continue
            try:
                node = dag.node(step_id)
            except KeyError:
                log.warning(f"_active.json references unknown step '{step_id}', skipping")
                continue
            node.step.load_params(values)

        log.info(f"Loaded _active.json (dirty={self._dirty}, based_on={self._based_on!r})")

    def save_active(self, dag: DAG) -> None:
        """Serialize current registry state to _active.json."""
        self._dir.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "_meta": {
                "dirty": self._dirty,
                "based_on": self._based_on,
            },
            **_snapshot_params(dag),
        }
        (self._dir / "_active.json").write_text(json.dumps(data, indent=2, cls=_Encoder))
        log.debug(f"Saved _active.json (dirty={self._dirty})")

    def save_preset(self, name: str, dag: DAG) -> None:
        """Save current params as a named preset and mark active as clean."""
        self._dir.mkdir(parents=True, exist_ok=True)
        snapshot = json.dumps(_snapshot_params(dag), indent=2, cls=_Encoder)
        (self._dir / f"{name}.json").write_text(snapshot)
        self._dirty = False
        self._based_on = name
        self.save_active(dag)
        log.info(f"Saved preset '{name}'")

    def load_preset(self, name: str, dag: DAG, *, save: bool = True) -> None:
        """Load a named preset into step registries and optionally update _active.json.

        Pass save=False to load params without writing to disk (e.g. during parallel builds).
        """
        preset_path = self._dir / f"{name}.json"
        if not preset_path.exists():
            raise FileNotFoundError(
                f"Preset '{name}' not found at {preset_path}. Available: {self.list_presets()}"
            )
        data: dict[str, Any] = json.loads(preset_path.read_text())
        for step_id, values in data.items():
            try:
                node = dag.node(step_id)
            except KeyError:
                log.warning(f"Preset '{name}' references unknown step '{step_id}', skipping")
                continue
            node.step.load_params(values)
        self._dirty = False
        self._based_on = name
        if save:
            self.save_active(dag)
        log.info(f"Loaded preset '{name}'")

    def reset(self, dag: DAG) -> None:
        """Reset all step params to their declared defaults and clear active state."""
        for node in dag.topo_sort():
            node.step.reset_params()
        self._dirty = False
        self._based_on = None
        self.save_active(dag)
        log.info("Reset to defaults (untitled)")

    def list_presets(self) -> list[str]:
        """Return sorted list of named preset names (without .json extension)."""
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.json") if p.stem != "_active")


# ---------------------------------------------------------------------------
# BuiltDAG preset I/O helpers (v3 functional pipeline API)
# ---------------------------------------------------------------------------


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
    for node in dag.topo_sort():
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


def save_preset_from_built(dag: BuiltDAG, presets_dir: str | Path, name: str) -> None:
    """Snapshot current BuiltNode.param_values to <name>.json."""
    presets_dir = Path(presets_dir)
    presets_dir.mkdir(parents=True, exist_ok=True)
    snapshot = json.dumps(_snapshot_params_built(dag), indent=2, cls=_Encoder)
    (presets_dir / f"{name}.json").write_text(snapshot)
    log.info(f"Saved preset '{name}' from BuiltDAG")
