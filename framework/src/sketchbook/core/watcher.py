"""watchdog integration — per-source-node file monitoring."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

log = logging.getLogger("sketchbook.watcher")


class _SourceFileHandler(FileSystemEventHandler):
    def __init__(self, path: Path, callback: Callable[[], None]) -> None:
        self._path = path
        self._callback = callback

    def _matches(self, src_path: str) -> bool:
        return Path(src_path).resolve() == self._path.resolve()

    def on_modified(self, event: FileModifiedEvent) -> None:
        if self._matches(event.src_path):
            log.info(f"Source file modified: {self._path}")
            self._callback()

    def on_created(self, event: FileCreatedEvent) -> None:
        # Finder replaces files via a create, not a modify
        if self._matches(event.src_path):
            log.info(f"Source file replaced: {self._path}")
            self._callback()

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if self._matches(event.src_path):
            log.info(f"Source file removed: {self._path}")
            self._callback()

    def on_moved(self, event: FileMovedEvent) -> None:
        if self._matches(event.src_path):
            # The watched file was renamed away — it's gone
            log.info(f"Source file moved away: {self._path}")
            self._callback()
        elif self._matches(event.dest_path):
            # Another file was renamed onto the watched path
            log.info(f"Source file swapped in: {self._path}")
            self._callback()


class Watcher:
    """Watches one or more source files and calls a callback when any change."""

    def __init__(self) -> None:
        self._observer = Observer()
        self._started = False

    def watch(self, path: str | Path, callback: Callable[[], None]) -> None:
        """Watch a file and call callback when it's modified."""
        path = Path(path)
        handler = _SourceFileHandler(path, callback)
        self._observer.schedule(handler, str(path.parent), recursive=False)
        log.info(f"Watching {path}")

    def start(self) -> None:
        """Start the file observer."""
        if not self._started:
            self._observer.start()
            self._started = True

    def stop(self) -> None:
        """Stop the file observer."""
        if self._started:
            self._observer.stop()
            self._observer.join()
            self._started = False
