"""Preset persistence: _active.json load/save and named preset CRUD."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sketchbook.core.dag import DAG
from sketchbook.core.params import Color

log = logging.getLogger("sketchbook.core.presets")


class _Encoder(json.JSONEncoder):
    """JSON encoder that serializes Color instances as hex strings."""

    def default(self, o: Any) -> Any:
        """Encode Color as its hex string representation."""
        if isinstance(o, Color):
            return str(o)
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

    def load_preset(self, name: str, dag: DAG) -> None:
        """Load a named preset into step registries and update _active.json."""
        preset_path = self._dir / f"{name}.json"
        if not preset_path.exists():
            raise FileNotFoundError(
                f"Preset '{name}' not found at {preset_path}. "
                f"Available: {self.list_presets()}"
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
        return sorted(
            p.stem
            for p in self._dir.glob("*.json")
            if p.stem != "_active"
        )
