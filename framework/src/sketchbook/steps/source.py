"""SourceFile step — holds a watched path and delegates loading to a caller-supplied loader."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sketchbook.core.step import PipelineStep


class SourceFile(PipelineStep):
    """Reads a file from disk by delegating to a caller-supplied loader function.

    The loader is the sketch's responsibility. This step exists to mark nodes
    that the file watcher should observe — the framework does not care what
    format the file is in.
    """

    def __init__(self, path: str | Path, loader: Callable[[Path], Any] | None = None) -> None:
        self._path = Path(path)
        self._loader = loader
        super().__init__()

    def setup(self) -> None:
        """No inputs — this is a source node."""

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Any:
        """Load and return the file using the provided loader."""
        if self._loader is None:
            raise ValueError(
                f"SourceFile at '{self._path}' has no loader. "
                "Pass loader= to sketch.source() to supply one."
            )
        return self._loader(self._path)
