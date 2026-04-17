"""@step, @sketch, and supporting dataclasses for the functional pipeline API."""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from sketchbook.core.building_dag import _active_dag


@dataclass
class Param:
    """Metadata for a tunable step parameter declared via Annotated[T, Param(...)].

    Unused in Increment 1 but defined here so Annotated annotations compile
    without errors.
    """

    min: float | None = None
    max: float | None = None
    step: float | None = None
    label: str | None = None
    debounce: int | None = None
    options: list[str] | None = field(default=None)


@dataclass
class SketchContext:
    """Runtime context passed to steps that request it."""

    mode: Literal["dev", "build"]


@dataclass
class SketchMeta:
    """Metadata stamped on a @sketch-decorated function."""

    date: str
    name: str
    description: str


def sketch(date: str) -> Callable:
    """Decorator factory that marks a function as a sketch entry point.

    Stamps ``__is_sketch__ = True`` and ``__sketch_meta__`` on the function.
    Name is derived from ``fn.__name__``; description from the docstring.
    """

    def decorator(fn: Callable) -> Callable:
        fn.__is_sketch__ = True  # type: ignore[attr-defined]
        fn.__sketch_meta__ = SketchMeta(  # type: ignore[attr-defined]
            date=date,
            name=fn.__name__,
            description=(fn.__doc__ or "").strip(),
        )
        return fn

    return decorator


def step(fn: Callable) -> Callable:
    """Mark a function as a pipeline step.

    - Called *outside* a ``building_sketch()`` context: executes immediately
      and returns the real result.
    - Called *inside* a ``building_sketch()`` context: records the call in the
      active ``BuildingDAG`` and returns a ``Proxy`` for the deferred result.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        dag = _active_dag.get()
        if dag is None:
            return fn(*args, **kwargs)
        return dag.record_step(fn, args, kwargs)

    # Preserve the original function for introspection (signature, annotations).
    wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
    return wrapper
