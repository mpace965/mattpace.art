"""Sketch discovery — scan a directory for @sketch-decorated functions."""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import sys
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("sketchbook.discovery")


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
