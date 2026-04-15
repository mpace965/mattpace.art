"""Unit tests for sketch discovery helpers."""

from __future__ import annotations

import sys
import textwrap
import types
from pathlib import Path

import pytest

from sketchbook import Sketch
from sketchbook.discovery import discover_sketch_fns, discover_sketches, find_sketch_class


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

    result = find_sketch_class(module)
    assert result is _FakeSketch


def test_returns_none_for_module_without_sketch() -> None:
    """Returns None when no Sketch subclass is present."""
    module = types.ModuleType("empty_module")

    result = find_sketch_class(module)
    assert result is None


def test_does_not_return_sketch_base_class() -> None:
    """Does not return the Sketch base class itself, only subclasses."""
    module = types.ModuleType("base_module")
    module.Sketch = Sketch  # type: ignore[attr-defined]

    result = find_sketch_class(module)
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

    result = find_sketch_class(module)
    assert result is not None
    assert issubclass(result, Sketch)
    assert result is not Sketch


# ---------------------------------------------------------------------------
# discover_sketches integration tests
# ---------------------------------------------------------------------------

_SKETCH_SRC = textwrap.dedent("""\
    from sketchbook import Sketch

    class MySketch(Sketch):
        name = "My"
        description = "test sketch"
        date = "2026-01-01"

        def build(self) -> None:
            pass
""")

_NON_SKETCH_SRC = textwrap.dedent("""\
    def helper():
        pass
""")


@pytest.fixture()
def sketch_package(tmp_path: Path) -> Path:
    """Create a minimal sketch package on disk and clean up sys.modules after."""
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mysketch.py").write_text(_SKETCH_SRC)
    yield pkg
    # Remove imported modules so they don't bleed into other tests.
    for key in list(sys.modules):
        if key == "mypkg" or key.startswith("mypkg."):
            del sys.modules[key]
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))


@pytest.fixture()
def empty_package(tmp_path: Path) -> Path:
    """Create a package with no Sketch subclasses."""
    pkg = tmp_path / "emptypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "helper.py").write_text(_NON_SKETCH_SRC)
    yield pkg
    for key in list(sys.modules):
        if key == "emptypkg" or key.startswith("emptypkg."):
            del sys.modules[key]
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))


def test_discover_sketches_finds_sketch_class(sketch_package: Path) -> None:
    """discover_sketches returns a dict mapping slug to Sketch subclass."""
    result = discover_sketches(sketch_package)
    assert "mysketch" in result
    assert issubclass(result["mysketch"], Sketch)
    assert result["mysketch"] is not Sketch


def test_discover_sketches_skips_non_sketch_modules(empty_package: Path) -> None:
    """discover_sketches skips modules that contain no Sketch subclass."""
    result = discover_sketches(empty_package)
    assert result == {}


def test_discover_sketches_empty_directory(tmp_path: Path) -> None:
    """discover_sketches returns empty dict for a package with no submodules."""
    pkg = tmp_path / "barepackage"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    result = discover_sketches(pkg)
    assert result == {}
    # cleanup
    sys.modules.pop("barepackage", None)
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))


# ---------------------------------------------------------------------------
# discover_sketch_fns tests
# ---------------------------------------------------------------------------

_SKETCH_FN_SRC = textwrap.dedent("""\
    from sketchbook.core.decorators import sketch

    @sketch(date="2026-01-01")
    def my_sketch_fn() -> None:
        \"\"\"A v3 sketch function.\"\"\"
        pass
""")

_PLAIN_FN_SRC = textwrap.dedent("""\
    def helper():
        pass
""")

_SKETCH_CLASS_SRC = textwrap.dedent("""\
    from sketchbook import Sketch

    class MyOldSketch(Sketch):
        name = "Old"
        description = "old style"
        date = "2026-01-01"

        def build(self) -> None:
            pass
""")


@pytest.fixture()
def fn_sketch_package(tmp_path: Path) -> Path:
    """Package with one @sketch-decorated function."""
    pkg = tmp_path / "fnpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "myfnsketch.py").write_text(_SKETCH_FN_SRC)
    yield pkg
    for key in list(sys.modules):
        if key == "fnpkg" or key.startswith("fnpkg."):
            del sys.modules[key]
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))


@pytest.fixture()
def plain_fn_package(tmp_path: Path) -> Path:
    """Package with only plain functions (no @sketch)."""
    pkg = tmp_path / "plainpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "helper.py").write_text(_PLAIN_FN_SRC)
    yield pkg
    for key in list(sys.modules):
        if key == "plainpkg" or key.startswith("plainpkg."):
            del sys.modules[key]
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))


@pytest.fixture()
def class_sketch_package(tmp_path: Path) -> Path:
    """Package with a Sketch subclass (old-style)."""
    pkg = tmp_path / "classpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "oldsketch.py").write_text(_SKETCH_CLASS_SRC)
    yield pkg
    for key in list(sys.modules):
        if key == "classpkg" or key.startswith("classpkg."):
            del sys.modules[key]
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))


def test_discover_sketch_fns_finds_decorated_function(fn_sketch_package: Path) -> None:
    """discover_sketch_fns returns {slug: fn} for @sketch-decorated functions."""
    result = discover_sketch_fns(fn_sketch_package)
    assert "myfnsketch" in result
    fn = result["myfnsketch"]
    assert callable(fn)
    assert getattr(fn, "__is_sketch__", False) is True


def test_discover_sketch_fns_ignores_plain_functions(plain_fn_package: Path) -> None:
    """discover_sketch_fns ignores modules with no @sketch-decorated callables."""
    result = discover_sketch_fns(plain_fn_package)
    assert result == {}


def test_discover_sketch_fns_ignores_sketch_classes(class_sketch_package: Path) -> None:
    """discover_sketch_fns ignores old-style Sketch subclasses."""
    result = discover_sketch_fns(class_sketch_package)
    assert result == {}
