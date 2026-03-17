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
