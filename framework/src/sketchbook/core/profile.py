"""Execution profiles — quality settings resolved per execution mode."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import ClassVar

log = logging.getLogger("sketchbook.profile")


@dataclass(frozen=True)
class ExecutionProfile:
    """Immutable bag of execution-quality settings for a given mode."""

    draft_scale: float
    compress_level: int


class ProfileRegistry:
    """Resolves an ExecutionProfile for a named mode using a three-level cascade.

    Cascade order:
      1. Sketch-supplied overrides (no warning).
      2. Framework mode default (warns).
      3. Framework 'base' default (warns).
      4. RuntimeError — should never happen if framework defaults are intact.
    """

    _FRAMEWORK_DEFAULTS: ClassVar[dict[str, ExecutionProfile]] = {
        "base": ExecutionProfile(draft_scale=1.0, compress_level=0),
        "dev": ExecutionProfile(draft_scale=1.0, compress_level=0),
        "build": ExecutionProfile(draft_scale=1.0, compress_level=9),
    }

    def __init__(self, sketch_profiles: dict[str, ExecutionProfile]) -> None:
        self._sketch = sketch_profiles

    def resolve(self, mode: str) -> ExecutionProfile:
        """Return the ExecutionProfile for mode, falling back through the cascade."""
        if mode in self._sketch:
            return self._sketch[mode]

        if mode in self._FRAMEWORK_DEFAULTS:
            log.warning(
                f"No sketch-level profile for mode '{mode}'; "
                f"falling back to framework default."
            )
            return self._FRAMEWORK_DEFAULTS[mode]

        if "base" in self._FRAMEWORK_DEFAULTS:
            log.warning(
                f"Unknown mode '{mode}' and no sketch override; "
                f"falling back to framework 'base' profile."
            )
            return self._FRAMEWORK_DEFAULTS["base"]

        raise RuntimeError(
            f"ProfileRegistry has no entry for mode '{mode}' and no 'base' fallback. "
            f"This is a framework bug."
        )
