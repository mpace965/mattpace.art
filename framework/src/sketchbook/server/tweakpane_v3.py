"""Adapter functions for converting v3 ParamSpec to Tweakpane-compatible UI schema."""

from __future__ import annotations

from typing import Any

from sketchbook.core.built_dag import BuiltNode, ParamSpec


def param_spec_to_tweakpane(spec: ParamSpec, current_value: Any) -> dict[str, Any]:
    """Return a Tweakpane-compatible schema dict for a single ParamSpec."""
    if hasattr(current_value, "to_tweakpane"):
        wire_value = current_value.to_tweakpane()
    else:
        wire_value = current_value

    d: dict[str, Any] = {
        "type": spec.type.__name__,
        "value": wire_value,
    }
    p = spec.param
    if p.min is not None:
        d["min"] = p.min
    if p.max is not None:
        d["max"] = p.max
    if p.step is not None:
        d["step"] = p.step
    if p.label is not None:
        d["label"] = p.label
    if p.debounce is not None:
        d["debounce"] = p.debounce
    if p.options is not None:
        d["options"] = p.options
    return d


def built_node_to_tweakpane(node: BuiltNode) -> dict[str, dict[str, Any]]:
    """Return a Tweakpane schema dict for all params in *node*."""
    return {
        spec.name: param_spec_to_tweakpane(spec, node.param_values.get(spec.name, spec.default))
        for spec in node.param_schema
    }
