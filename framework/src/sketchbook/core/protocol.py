"""SketchValueProtocol — structural protocol for pipeline step outputs."""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable


@runtime_checkable
class SketchValueProtocol(Protocol):
    """Structural protocol for values produced by pipeline steps.

    Any object with ``extension``, ``kind``, and ``to_bytes`` satisfies this
    protocol. ``kind`` declares how the dev server should display the output
    (e.g. ``"image"`` or ``"text"``).
    """

    extension: str
    kind: str

    def to_bytes(self, mode: Literal["dev", "build"]) -> bytes:
        """Serialize the value to bytes for the given build mode."""
        ...


def output_kind(value: Any) -> str:
    """Return the display kind for a step output value.

    Reads ``value.kind`` if the value satisfies SketchValueProtocol;
    falls back to ``"text"`` for plain Python values.
    """
    if isinstance(value, SketchValueProtocol):
        return value.kind
    return "text"
