"""Parameter definitions and registry for pipeline steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_BOOL_TRUE_STRINGS: frozenset[str] = frozenset({"true", "1", "yes", "on"})
_BOOL_FALSE_STRINGS: frozenset[str] = frozenset({"false", "0", "no", "off"})


def _coerce_bool(value: Any) -> bool:
    """Coerce a value to bool with explicit string handling.

    Accepts actual bools and ints directly. For strings, recognises
    'true'/'1'/'yes'/'on' → True and 'false'/'0'/'no'/'off' → False
    (case-insensitive). Raises ValueError for any other string.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in _BOOL_TRUE_STRINGS:
            return True
        if lowered in _BOOL_FALSE_STRINGS:
            return False
        raise ValueError(
            f"Cannot coerce string '{value}' to bool. "
            f"Accepted true values: {sorted(_BOOL_TRUE_STRINGS)}. "
            f"Accepted false values: {sorted(_BOOL_FALSE_STRINGS)}."
        )
    return bool(value)


@dataclass
class ParamDef:
    """Declares a single parameter on a step."""

    name: str
    type: type
    default: Any
    min: Any = None
    max: Any = None
    step: Any = None
    label: str | None = None
    debounce: int | None = None
    options: list[str] | None = None



class ParamRegistry:
    """Holds param definitions and current values for a step."""

    def __init__(self) -> None:
        self._params: dict[str, ParamDef] = {}
        self._values: dict[str, Any] = {}

    def add(self, param: ParamDef) -> None:
        """Register a param definition with its default value."""
        self._params[param.name] = param
        self._values[param.name] = param.default

    def get_value(self, name: str) -> Any:
        """Return the current value for a param."""
        return self._values[name]

    def set_value(self, name: str, value: Any) -> None:
        """Set the current value for a param, coercing to the declared type."""
        if name not in self._params:
            raise KeyError(f"Unknown param '{name}'. Available: {list(self._params)}")
        param = self._params[name]
        coerced = _coerce_bool(value) if param.type is bool else param.type(value)
        if param.options is not None and coerced not in param.options:
            raise ValueError(f"Value '{coerced}' is not a valid option for '{name}'. Must be one of: {param.options}")
        self._values[name] = coerced

    def values(self) -> dict[str, Any]:
        """Return a snapshot of all current param values."""
        return dict(self._values)

    def load_values(self, data: dict[str, Any]) -> None:
        """Bulk-load values from a dict, coercing each to its declared type."""
        for name, value in data.items():
            if name in self._params:
                self._values[name] = self._params[name].type(value)

    def reset_to_defaults(self) -> None:
        """Reset all values to their declared defaults."""
        for name, param in self._params.items():
            self._values[name] = param.default

    @property
    def params(self) -> dict[str, ParamDef]:
        """Return a snapshot of all param definitions, keyed by name."""
        return dict(self._params)

    def override(self, name: str, **fields: Any) -> None:
        """Override specific fields of an existing param definition.

        Accepts any subset of ParamDef fields (min, max, step, label, debounce, default).
        If default is overridden, the current value is also updated.
        """
        if name not in self._params:
            raise KeyError(f"Unknown param '{name}'. Available: {list(self._params)}")
        p = self._params[name]
        allowed = {"min", "max", "step", "label", "debounce", "default", "options"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown override fields for param '{name}': {unknown}")
        for field, value in fields.items():
            setattr(p, field, value)
        if "default" in fields:
            self._values[name] = p.type(fields["default"])
