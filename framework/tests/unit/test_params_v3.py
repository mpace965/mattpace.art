"""Unit tests for coerce_param()."""

from __future__ import annotations

import pytest

from sketchbook.core.built_dag import ParamSpec
from sketchbook.core.decorators import Param
from sketchbook.core.introspect import coerce_param


def test_coerce_int() -> None:
    """coerce_param coerces int values and int-like strings."""
    spec = ParamSpec(name="level", type=int, default=128, param=Param())
    assert coerce_param(spec, 64) == 64
    assert coerce_param(spec, "32") == 32


def test_coerce_float() -> None:
    """coerce_param coerces float values and float-like strings."""
    spec = ParamSpec(name="sigma", type=float, default=1.0, param=Param())
    assert coerce_param(spec, "2.5") == 2.5


def test_coerce_bool_true_string() -> None:
    """coerce_param coerces truthy strings to True."""
    spec = ParamSpec(name="flag", type=bool, default=False, param=Param())
    assert coerce_param(spec, "true") is True


def test_coerce_bool_false_string() -> None:
    """coerce_param coerces falsy strings to False."""
    spec = ParamSpec(name="flag", type=bool, default=True, param=Param())
    assert coerce_param(spec, "false") is False


def test_coerce_bool_invalid_string_raises() -> None:
    """coerce_param raises ValueError for unrecognised bool strings."""
    spec = ParamSpec(name="flag", type=bool, default=False, param=Param())
    with pytest.raises(ValueError):
        coerce_param(spec, "maybe")


def test_coerce_str_passthrough() -> None:
    """coerce_param passes str values through unchanged."""
    spec = ParamSpec(name="mode", type=str, default="fast", param=Param())
    assert coerce_param(spec, "slow") == "slow"
