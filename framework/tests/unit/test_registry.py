"""Unit tests for SketchRegistry error handling on lazy load."""

from __future__ import annotations

from pathlib import Path

from sketchbook.core.sketch import Sketch
from sketchbook.server.registry import SketchRegistry


class _GoodSketch(Sketch):
    name = "Good"
    description = ""
    date = "2026-01-01"

    def build(self) -> None:
        pass


class _BrokenSketch(Sketch):
    name = "Broken"
    description = ""
    date = "2026-01-01"

    def build(self) -> None:
        raise RuntimeError("build exploded")


def _registry(tmp_path: Path, candidates: dict) -> SketchRegistry:
    return SketchRegistry({}, sketches_dir=tmp_path, candidates=candidates)


def test_failed_load_stores_exception(tmp_path: Path) -> None:
    """get_sketch_error returns the exception raised during lazy load."""
    (tmp_path / "broken").mkdir()
    reg = _registry(tmp_path, {"broken": _BrokenSketch})

    reg.get_sketch("broken")

    exc = reg.get_sketch_error("broken")
    assert isinstance(exc, RuntimeError)
    assert "build exploded" in str(exc)


def test_failed_load_keeps_candidate(tmp_path: Path) -> None:
    """The candidate is not evicted after a failed load."""
    (tmp_path / "broken").mkdir()
    reg = _registry(tmp_path, {"broken": _BrokenSketch})

    reg.get_sketch("broken")

    assert "broken" in reg.candidates


def test_failed_load_returns_none(tmp_path: Path) -> None:
    """get_sketch returns None when the load fails."""
    (tmp_path / "broken").mkdir()
    reg = _registry(tmp_path, {"broken": _BrokenSketch})

    result = reg.get_sketch("broken")

    assert result is None


def test_no_error_for_unknown_sketch(tmp_path: Path) -> None:
    """get_sketch_error returns None for a sketch that was never attempted."""
    reg = _registry(tmp_path, {})
    assert reg.get_sketch_error("unknown") is None


def test_successful_load_clears_previous_error(tmp_path: Path) -> None:
    """If a sketch loads successfully, any previously stored error is cleared."""
    sketch_dir = tmp_path / "good"
    sketch_dir.mkdir()
    reg = _registry(tmp_path, {"good": _BrokenSketch})

    # Prime a failure by swapping in the broken class, then loading.
    reg.get_sketch("good")
    assert reg.get_sketch_error("good") is not None

    # Now swap to the working class and re-register as candidate.
    reg.candidates["good"] = _GoodSketch
    reg.get_sketch("good")

    assert reg.get_sketch_error("good") is None
