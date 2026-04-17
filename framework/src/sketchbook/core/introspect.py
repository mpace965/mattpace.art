"""Introspection helpers — extract typed input and param specs from step function signatures."""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from sketchbook.core.built_dag import ParamSpec


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


def extract_params(fn: Callable) -> list[ParamSpec]:
    """Return ParamSpec list for keyword-only Annotated[T, Param(...)] parameters of *fn*.

    Rules:
    - Only KEYWORD_ONLY parameters are included.
    - Parameters annotated as ``SketchContext`` are excluded.
    - Only parameters whose annotation is (or contains) ``Annotated[T, Param(...)]`` are
      included; bare keyword args without a ``Param`` metadata are silently skipped.
    - A parameter without a default value raises ``ValueError``.
    """
    from sketchbook.core.decorators import Param, SketchContext

    unwrapped = getattr(fn, "__wrapped__", fn)

    try:
        hints = typing.get_type_hints(unwrapped, include_extras=True)
    except Exception:
        hints = {}

    sig = inspect.signature(unwrapped)
    specs: list[ParamSpec] = []

    for name, param in sig.parameters.items():
        if param.kind != inspect.Parameter.KEYWORD_ONLY:
            continue

        annotation = hints.get(name, inspect.Parameter.empty)

        # Strip Optional wrapper (T | None) to get the inner type.
        inner = annotation
        if _is_optional_annotation(annotation):
            args = [a for a in typing.get_args(annotation) if a is not type(None)]
            inner = args[0] if args else inspect.Parameter.empty

        # Skip SketchContext parameters.
        if inner is SketchContext:
            continue

        # Must be Annotated[T, Param(...)].
        if typing.get_origin(inner) is not Annotated:
            continue

        annotated_args = typing.get_args(inner)
        if len(annotated_args) < 2:
            continue

        base_type = annotated_args[0]
        param_meta = next((a for a in annotated_args[1:] if isinstance(a, Param)), None)
        if param_meta is None:
            continue

        default = param.default
        if default is inspect.Parameter.empty:
            raise ValueError(
                f"Param '{name}' must have a default value — add '= <default>' to the signature."
            )

        specs.append(ParamSpec(name=name, type=base_type, default=default, param=param_meta))

    return specs


_BOOL_TRUE_STRINGS: frozenset[str] = frozenset({"true", "1", "yes", "on"})
_BOOL_FALSE_STRINGS: frozenset[str] = frozenset({"false", "0", "no", "off"})


def _coerce_bool(value: Any) -> bool:
    """Coerce a value to bool with explicit string handling."""
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


def coerce_param(spec: ParamSpec, raw: Any) -> Any:
    """Coerce *raw* to the type declared in *spec*.

    Delegates bool coercion to ``_coerce_bool`` for robust string handling.
    For int, float, and str, calls the type constructor directly.
    Unknown types are returned unchanged.
    """
    if spec.type is bool:
        return _coerce_bool(raw)
    if spec.type in (int, float, str):
        return spec.type(raw)
    if not isinstance(raw, spec.type):
        return spec.type(raw)
    return raw
