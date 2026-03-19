"""Adapter functions for converting domain params to Tweakpane-compatible UI schema."""

from __future__ import annotations

from typing import Any

from sketchbook.core.params import ParamDef, ParamRegistry


def param_def_to_tweakpane(param: ParamDef, current_value: Any) -> dict[str, Any]:
    """Return a Tweakpane-compatible schema dict for a single param definition."""
    d: dict[str, Any] = {
        "type": param.type.__name__,
        "value": current_value,
    }
    if param.min is not None:
        d["min"] = param.min
    if param.max is not None:
        d["max"] = param.max
    if param.step is not None:
        d["step"] = param.step
    if param.label is not None:
        d["label"] = param.label
    if param.debounce is not None:
        d["debounce"] = param.debounce
    if param.options is not None:
        d["options"] = param.options
    return d


def param_registry_to_tweakpane(registry: ParamRegistry) -> dict[str, dict[str, Any]]:
    """Return a Tweakpane-compatible schema for all params in a registry."""
    return {
        name: param_def_to_tweakpane(param, registry.get_value(name))
        for name, param in registry.params.items()
    }
