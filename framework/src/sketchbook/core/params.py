"""Parameter definitions and registry for pipeline steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Color:
    """An RGB color value backed by a hex string (e.g. '#ff69b4')."""

    r: int
    g: int
    b: int

    def __init__(self, value: str) -> None:
        """Parse a '#rrggbb' hex string into r, g, b components."""
        v = value.strip()
        if not (v.startswith("#") and len(v) == 7):
            raise ValueError(f"Color value must be a '#rrggbb' hex string, got: {value!r}")
        try:
            self.r = int(v[1:3], 16)
            self.g = int(v[3:5], 16)
            self.b = int(v[5:7], 16)
        except ValueError:
            raise ValueError(f"Color value must be a '#rrggbb' hex string, got: {value!r}")

    def __str__(self) -> str:
        """Return the lowercase '#rrggbb' hex representation."""
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def to_bgr(self) -> tuple[int, int, int]:
        """Return the color as a (blue, green, red) tuple for use with OpenCV."""
        return (self.b, self.g, self.r)

    def to_tweakpane(self) -> str:
        """Return the hex string representation for Tweakpane."""
        return str(self)


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

    def tweakpane_value(self, value: Any) -> Any:
        """Return the wire representation of value for Tweakpane.

        Rich types may implement to_tweakpane() to control their representation.
        Plain types are passed through as-is.
        """
        if hasattr(value, "to_tweakpane"):
            return value.to_tweakpane()
        return value


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
        if isinstance(value, param.type):
            coerced = value
        elif param.type is bool:
            coerced = _coerce_bool(value)
        else:
            coerced = param.type(value)
        if param.options is not None and coerced not in param.options:
            raise ValueError(
                f"Value '{coerced}' is not a valid option for '{name}'. Options: {param.options}"
            )
        self._values[name] = coerced

    def values(self) -> dict[str, Any]:
        """Return a snapshot of all current param values."""
        return dict(self._values)

    def load_values(self, data: dict[str, Any]) -> None:
        """Bulk-load values from a dict, coercing each to its declared type."""
        for name, value in data.items():
            if name in self._params:
                param = self._params[name]
                if isinstance(value, param.type):
                    self._values[name] = value
                else:
                    self._values[name] = param.type(value)

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
