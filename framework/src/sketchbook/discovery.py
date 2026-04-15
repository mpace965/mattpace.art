"""Sketch discovery — scan a directory for Sketch subclasses or @sketch functions."""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import sys
import time
import types
from collections.abc import Callable
from pathlib import Path

from sketchbook.core.sketch import Sketch

log = logging.getLogger("sketchbook.discovery")


def find_sketch_class(module: types.ModuleType) -> type[Sketch] | None:
    """Return the first Sketch subclass found in *module*, or None."""
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, Sketch) and obj is not Sketch:
            return obj
    return None


def discover_sketches(sketches_dir: Path) -> dict[str, type[Sketch]]:
    """Scan *sketches_dir* submodules for Sketch subclasses.

    Only imports modules and collects classes — does not instantiate or execute.
    The directory's parent is added to ``sys.path`` so the package is importable,
    and the package name is derived from the directory name.
    """
    parent = str(sketches_dir.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    package_name = sketches_dir.name
    importlib.import_module(package_name)

    t0 = time.perf_counter()
    candidates: dict[str, type[Sketch]] = {}
    for mod_info in pkgutil.iter_modules([str(sketches_dir)]):
        slug = mod_info.name
        module = importlib.import_module(f"{package_name}.{slug}")
        cls = find_sketch_class(module)
        if cls is not None:
            candidates[slug] = cls
    log.info(f"Discovered {len(candidates)} sketch modules in {time.perf_counter() - t0:.2f}s")
    return candidates


def discover_sketch_fns(sketches_dir: Path) -> dict[str, Callable]:
    """Scan submodules of *sketches_dir* for callables stamped with ``__is_sketch__``.

    Returns a mapping of slug → function for all discovered @sketch-decorated
    functions. Ignores plain functions, Sketch subclasses, and any other objects.
    """
    parent = str(sketches_dir.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    package_name = sketches_dir.name
    importlib.import_module(package_name)

    candidates: dict[str, Callable] = {}
    for mod_info in pkgutil.iter_modules([str(sketches_dir)]):
        slug = mod_info.name
        module = importlib.import_module(f"{package_name}.{slug}")
        for _, obj in inspect.getmembers(module):
            if callable(obj) and not inspect.isclass(obj) and getattr(obj, "__is_sketch__", False):
                candidates[slug] = obj
                break
    return candidates
