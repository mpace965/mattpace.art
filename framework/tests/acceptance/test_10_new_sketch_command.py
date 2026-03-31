"""Acceptance test for the new-sketch scaffolding command.

Verifies end-to-end: given a name, the command produces a valid, importable
sketch directory with the expected structure.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from sketchbook.scaffold import scaffold_sketch


def _load_module(path: Path, module_name: str):
    """Load a Python file as a module without side effects."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestNewSketchScaffold:
    """End-to-end scaffold acceptance tests."""

    def test_creates_expected_directory_structure(self, tmp_path: Path) -> None:
        """scaffold_sketch produces assets/, presets/, and __init__.py."""
        scaffold_sketch("my-sketch", sketches_dir=tmp_path)

        sketch_dir = tmp_path / "my-sketch"
        assert sketch_dir.is_dir()
        assert (sketch_dir / "__init__.py").is_file()
        assert (sketch_dir / "assets").is_dir()
        assert (sketch_dir / "presets").is_dir()
        assert (sketch_dir / "presets" / "_active.json").is_file()

    def test_active_preset_is_empty_json_object(self, tmp_path: Path) -> None:
        """The generated _active.json starts as an empty object."""
        scaffold_sketch("my-sketch", sketches_dir=tmp_path)

        active = json.loads((tmp_path / "my-sketch" / "presets" / "_active.json").read_text())
        assert active == {}

    def test_generated_module_is_importable(self, tmp_path: Path) -> None:
        """The generated __init__.py is syntactically valid Python."""
        scaffold_sketch("new-thing", sketches_dir=tmp_path)

        mod = _load_module(tmp_path / "new-thing" / "__init__.py", "new_thing_scaffold_test")
        assert mod is not None

    def test_generated_module_contains_sketch_subclass(self, tmp_path: Path) -> None:
        """The generated module exports exactly one Sketch subclass."""
        import inspect

        from sketchbook.core.sketch import Sketch

        scaffold_sketch("my-sketch", sketches_dir=tmp_path)

        mod = _load_module(tmp_path / "my-sketch" / "__init__.py", "my_sketch_scaffold_test")
        sketch_classes = [
            obj
            for _, obj in inspect.getmembers(mod, inspect.isclass)
            if issubclass(obj, Sketch) and obj is not Sketch
        ]
        assert len(sketch_classes) == 1
        assert sketch_classes[0].name == "my-sketch"

    def test_symlinks_shared_assets(self, tmp_path: Path) -> None:
        """Assets from a shared assets/ dir are symlinked into the sketch."""
        shared = tmp_path / "assets"
        shared.mkdir()
        (shared / "texture.jpg").write_bytes(b"fake")
        (shared / "grain.png").write_bytes(b"fake")

        scaffold_sketch("my-sketch", sketches_dir=tmp_path)

        sketch_assets = tmp_path / "my-sketch" / "assets"
        assert (sketch_assets / "texture.jpg").is_symlink()
        assert (sketch_assets / "grain.png").is_symlink()
        # Symlinks resolve back to the shared library
        assert (sketch_assets / "texture.jpg").resolve() == (shared / "texture.jpg").resolve()

    def test_no_symlinks_when_no_shared_assets(self, tmp_path: Path) -> None:
        """When there's no shared assets/ dir, the sketch assets/ is still created."""
        scaffold_sketch("my-sketch", sketches_dir=tmp_path)

        sketch_assets = tmp_path / "my-sketch" / "assets"
        assert sketch_assets.is_dir()
        assert list(sketch_assets.iterdir()) == []

    def test_raises_on_duplicate_name(self, tmp_path: Path) -> None:
        """scaffold_sketch refuses to overwrite an existing sketch directory."""
        scaffold_sketch("my-sketch", sketches_dir=tmp_path)

        with pytest.raises(FileExistsError):
            scaffold_sketch("my-sketch", sketches_dir=tmp_path)
