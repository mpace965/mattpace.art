"""SketchValueProtocol — structural protocol for pipeline step outputs."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable


@runtime_checkable
class SketchValueProtocol(Protocol):
    """Structural protocol for values produced by pipeline steps.

    Any object with ``extension`` and ``to_bytes`` satisfies this protocol.
    ``to_html`` is a convention for rendering the value in a browser but is
    not required — structural matching passes without it.
    """

    extension: str

    def to_bytes(self, mode: Literal["dev", "build"]) -> bytes:
        """Serialize the value to bytes for the given build mode."""
        ...
