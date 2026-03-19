"""PipelineStep base class."""

from __future__ import annotations

from typing import Any

from sketchbook.core.params import ParamDef, ParamRegistry


class InputSpec:
    """Declares an input slot on a step."""

    def __init__(self, name: str, type: type, optional: bool = False) -> None:
        self.name = name
        self.type = type
        self.optional = optional


class PipelineStep:
    """Base class for all pipeline steps."""

    def __init__(self) -> None:
        self._inputs: dict[str, InputSpec] = {}
        self._param_registry: ParamRegistry = ParamRegistry()
        self.setup()

    def setup(self) -> None:
        """Declare inputs and parameters. Called once at build time."""

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Any:
        """Execute the step. Called every time inputs or params change."""
        raise NotImplementedError(f"{type(self).__name__} must implement process()")

    def add_input(self, name: str, type: type, optional: bool = False) -> None:
        """Declare an input slot."""
        self._inputs[name] = InputSpec(name, type, optional)

    def add_param(self, name: str, type: type, default: Any, label: str | None = None, debounce: int | None = None, **constraints: Any) -> None:
        """Declare a parameter with its type, default, optional label, optional debounce (ms), and optional constraints."""
        self._param_registry.add(ParamDef(name=name, type=type, default=default, label=label, debounce=debounce, **constraints))

    @property
    def input_specs(self) -> dict[str, InputSpec]:
        """Return declared input specs."""
        return dict(self._inputs)

    def param_values(self) -> dict[str, Any]:
        """Return a snapshot of all current param values."""
        return self._param_registry.values()

    def param_schema(self) -> dict[str, dict[str, Any]]:
        """Return the UI schema dict for all params."""
        return self._param_registry.to_schema_dict()

    def load_params(self, data: dict[str, Any]) -> None:
        """Bulk-load param values from a dict, coercing each to its declared type."""
        self._param_registry.load_values(data)

    def set_param(self, name: str, value: Any) -> None:
        """Set a single param value, coercing to the declared type."""
        self._param_registry.set_value(name, value)

    def reset_params(self) -> None:
        """Reset all params to their declared defaults."""
        self._param_registry.reset_to_defaults()
