"""Introspection helpers — extract typed input specs from step function signatures."""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class InputSpec:
    """Describes one positional input of a pipeline step function."""

    name: str
    type: type
    optional: bool


def _is_optional_annotation(annotation: Any) -> bool:
    """Return True if *annotation* represents ``T | None`` (either form)."""
    args = typing.get_args(annotation)
    return bool(args) and type(None) in args


def extract_inputs(fn: Callable) -> list[InputSpec]:
    """Return InputSpec list for positional-or-keyword parameters of *fn*.

    Rules:
    - Only POSITIONAL_OR_KEYWORD and POSITIONAL_ONLY parameters are included.
    - Parameters whose annotation resolves to ``SketchContext`` are excluded.
    - A parameter is optional if its annotation is ``T | None`` and default is None.
    """
    from sketchbook.core.decorators import SketchContext

    # Unwrap @step's functools.wraps layer if present.
    unwrapped = getattr(fn, "__wrapped__", fn)

    try:
        hints = typing.get_type_hints(unwrapped)
    except Exception:
        hints = {}

    sig = inspect.signature(unwrapped)
    specs: list[InputSpec] = []

    for name, param in sig.parameters.items():
        if param.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        ):
            continue

        annotation = hints.get(name, inspect.Parameter.empty)

        # Exclude SketchContext parameters
        if annotation is SketchContext:
            continue

        optional = _is_optional_annotation(annotation) and param.default is None

        if optional:
            # Unwrap to the non-None type
            inner = [a for a in typing.get_args(annotation) if a is not type(None)]
            base_type: Any = inner[0] if inner else Any
        elif annotation is inspect.Parameter.empty:
            base_type = Any
        else:
            base_type = annotation

        specs.append(InputSpec(name=name, type=base_type, optional=optional))

    return specs
