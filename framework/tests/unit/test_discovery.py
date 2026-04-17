"""Unit tests for sketch discovery helpers."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from sketchbook.discovery import discover_sketch_fns

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

_CLASS_SRC = textwrap.dedent("""\
    class MyClass:
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
def class_package(tmp_path: Path) -> Path:
    """Package with a plain class (no @sketch)."""
    pkg = tmp_path / "classpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "myclass.py").write_text(_CLASS_SRC)
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


def test_discover_sketch_fns_ignores_plain_classes(class_package: Path) -> None:
    """discover_sketch_fns ignores plain classes without @sketch."""
    result = discover_sketch_fns(class_package)
    assert result == {}


def test_discover_sketch_fns_empty_directory(tmp_path: Path) -> None:
    """discover_sketch_fns returns empty dict for a package with no submodules."""
    pkg = tmp_path / "barepackage"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    result = discover_sketch_fns(pkg)
    assert result == {}
    sys.modules.pop("barepackage", None)
    if str(tmp_path) in sys.path:
        sys.path.remove(str(tmp_path))
