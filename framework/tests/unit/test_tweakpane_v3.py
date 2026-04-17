"""Unit tests for tweakpane adapter."""

from __future__ import annotations

from sketchbook.core.built_dag import BuiltNode, ParamSpec
from sketchbook.core.decorators import Param
from sketchbook.server.tweakpane import built_node_to_tweakpane, param_spec_to_tweakpane


def test_int_param_schema() -> None:
    """int param produces correct Tweakpane dict with min/max/step."""
    spec = ParamSpec(name="level", type=int, default=128, param=Param(min=0, max=255, step=1))
    d = param_spec_to_tweakpane(spec, 64)
    assert d["type"] == "int"
    assert d["value"] == 64
    assert d["min"] == 0
    assert d["max"] == 255
    assert d["step"] == 1


def test_float_param_schema() -> None:
    """float param produces correct Tweakpane dict."""
    spec = ParamSpec(name="sigma", type=float, default=1.0, param=Param(min=0.0, max=5.0))
    d = param_spec_to_tweakpane(spec, 2.5)
    assert d["type"] == "float"
    assert d["value"] == 2.5


def test_bool_param_schema() -> None:
    """bool param produces correct Tweakpane dict."""
    spec = ParamSpec(name="flag", type=bool, default=False, param=Param())
    d = param_spec_to_tweakpane(spec, True)
    assert d["type"] == "bool"
    assert d["value"] is True


def test_str_param_schema() -> None:
    """str param produces correct Tweakpane dict."""
    spec = ParamSpec(name="label", type=str, default="hello", param=Param())
    d = param_spec_to_tweakpane(spec, "world")
    assert d["type"] == "str"
    assert d["value"] == "world"


def test_optional_fields_absent_when_none() -> None:
    """min/max/step/label/debounce/options are omitted when None."""
    spec = ParamSpec(name="x", type=int, default=0, param=Param())
    d = param_spec_to_tweakpane(spec, 0)
    assert "min" not in d
    assert "max" not in d
    assert "step" not in d
    assert "label" not in d
    assert "debounce" not in d
    assert "options" not in d


def test_to_tweakpane_hook_called_for_rich_value() -> None:
    """If current_value has to_tweakpane(), call it instead of using raw value."""

    class Color:
        """Minimal rich value type."""

        def to_tweakpane(self) -> str:
            """Return hex color string."""
            return "#ff0000"

    spec = ParamSpec(name="color", type=Color, default=Color(), param=Param())
    d = param_spec_to_tweakpane(spec, Color())
    assert d["value"] == "#ff0000"


def test_built_node_to_tweakpane_all_params() -> None:
    """built_node_to_tweakpane returns a dict keyed by param name."""
    spec = ParamSpec(name="level", type=int, default=128, param=Param(min=0, max=255))
    node = BuiltNode(
        step_id="proc",
        fn=lambda: None,
        param_schema=[spec],
        param_values={"level": 64},
    )
    schema = built_node_to_tweakpane(node)
    assert "level" in schema
    assert schema["level"]["value"] == 64


def test_built_node_to_tweakpane_empty() -> None:
    """built_node_to_tweakpane returns empty dict for a node with no params."""
    node = BuiltNode(step_id="proc", fn=lambda: None)
    assert built_node_to_tweakpane(node) == {}
