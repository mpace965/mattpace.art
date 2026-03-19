"""Unit tests for sketch discovery helpers."""

from __future__ import annotations

import types

import pytest

from sketchbook import Sketch
from sketchbook.cli import _find_sketch_class_in_module


class _FakeSketch(Sketch):
    """Minimal Sketch subclass for discovery tests."""

    name = "Fake"
    description = "a fake sketch"
    date = "2026-01-01"

    def build(self) -> None:
        pass


def test_finds_sketch_subclass_in_module() -> None:
    """Returns the first Sketch subclass found in the module."""
    module = types.ModuleType("fake_module")
    module._FakeSketch = _FakeSketch  # type: ignore[attr-defined]

    result = _find_sketch_class_in_module(module)
    assert result is _FakeSketch


def test_returns_none_for_module_without_sketch() -> None:
    """Returns None when no Sketch subclass is present."""
    module = types.ModuleType("empty_module")

    result = _find_sketch_class_in_module(module)
    assert result is None


def test_does_not_return_sketch_base_class() -> None:
    """Does not return the Sketch base class itself, only subclasses."""
    module = types.ModuleType("base_module")
    module.Sketch = Sketch  # type: ignore[attr-defined]

    result = _find_sketch_class_in_module(module)
    assert result is None


def test_finds_first_subclass_when_multiple_present() -> None:
    """When multiple Sketch subclasses exist, returns the first one found."""

    class _AnotherSketch(Sketch):
        name = "Another"
        description = "another"
        date = "2026-01-01"

        def build(self) -> None:
            pass

    module = types.ModuleType("multi_module")
    module._FakeSketch = _FakeSketch  # type: ignore[attr-defined]
    module._AnotherSketch = _AnotherSketch  # type: ignore[attr-defined]

    result = _find_sketch_class_in_module(module)
    assert result is not None
    assert issubclass(result, Sketch)
    assert result is not Sketch
