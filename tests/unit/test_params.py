"""Unit tests for ParamDef and ParamRegistry."""

from __future__ import annotations

import pytest

from sketchbook.core.params import ParamDef, ParamRegistry


class TestParamDef:
    def test_basic_creation(self) -> None:
        p = ParamDef(name="threshold1", type=float, default=100.0, min=0.0, max=500.0)
        assert p.name == "threshold1"
        assert p.type is float
        assert p.default == 100.0
        assert p.min == 0.0
        assert p.max == 500.0

    def test_optional_constraints(self) -> None:
        p = ParamDef(name="flag", type=bool, default=True)
        assert p.min is None
        assert p.max is None
        assert p.step is None

    def test_to_dict_includes_value(self) -> None:
        p = ParamDef(name="x", type=float, default=1.0, min=0.0, max=10.0, step=0.5)
        d = p.to_dict(current_value=3.0)
        assert d["value"] == 3.0
        assert d["min"] == 0.0
        assert d["max"] == 10.0
        assert d["step"] == 0.5
        assert d["type"] == "float"


class TestParamRegistry:
    def test_add_and_get(self) -> None:
        reg = ParamRegistry()
        reg.add(ParamDef(name="k", type=int, default=5))
        assert reg.get_value("k") == 5

    def test_default_value(self) -> None:
        reg = ParamRegistry()
        reg.add(ParamDef(name="threshold1", type=float, default=100.0))
        assert reg.get_value("threshold1") == 100.0

    def test_set_value(self) -> None:
        reg = ParamRegistry()
        reg.add(ParamDef(name="threshold1", type=float, default=100.0))
        reg.set_value("threshold1", 42.0)
        assert reg.get_value("threshold1") == 42.0

    def test_set_unknown_param_raises(self) -> None:
        reg = ParamRegistry()
        with pytest.raises(KeyError):
            reg.set_value("nonexistent", 1.0)

    def test_type_coercion_float(self) -> None:
        reg = ParamRegistry()
        reg.add(ParamDef(name="x", type=float, default=0.0))
        reg.set_value("x", 5)  # int passed, should coerce to float
        assert isinstance(reg.get_value("x"), float)

    def test_type_coercion_int(self) -> None:
        reg = ParamRegistry()
        reg.add(ParamDef(name="k", type=int, default=3))
        reg.set_value("k", 7.9)  # float passed, should coerce to int
        assert isinstance(reg.get_value("k"), int)

    def test_values_dict(self) -> None:
        reg = ParamRegistry()
        reg.add(ParamDef(name="a", type=float, default=1.0))
        reg.add(ParamDef(name="b", type=int, default=2))
        assert reg.values() == {"a": 1.0, "b": 2}

    def test_to_schema_dict(self) -> None:
        reg = ParamRegistry()
        reg.add(ParamDef(name="threshold1", type=float, default=100.0, min=0.0, max=500.0))
        schema = reg.to_schema_dict()
        assert "threshold1" in schema
        assert schema["threshold1"]["value"] == 100.0
        assert schema["threshold1"]["min"] == 0.0
        assert schema["threshold1"]["max"] == 500.0

    def test_override_min_max(self) -> None:
        reg = ParamRegistry()
        reg.add(ParamDef(name="x", type=float, default=1.0, min=0.0, max=10.0))
        reg.override("x", min=2.0, max=5.0)
        schema = reg.to_schema_dict()
        assert schema["x"]["min"] == 2.0
        assert schema["x"]["max"] == 5.0

    def test_override_default_updates_value(self) -> None:
        reg = ParamRegistry()
        reg.add(ParamDef(name="x", type=float, default=1.0))
        reg.override("x", default=7.0)
        assert reg.get_value("x") == 7.0

    def test_override_unknown_param_raises(self) -> None:
        reg = ParamRegistry()
        with pytest.raises(KeyError):
            reg.override("nonexistent", min=0.0)

    def test_override_unknown_field_raises(self) -> None:
        reg = ParamRegistry()
        reg.add(ParamDef(name="x", type=float, default=1.0))
        with pytest.raises(ValueError):
            reg.override("x", bogus=99)

    def test_serialization_roundtrip(self) -> None:
        reg = ParamRegistry()
        reg.add(ParamDef(name="threshold1", type=float, default=100.0))
        reg.set_value("threshold1", 42.0)
        data = reg.values()

        reg2 = ParamRegistry()
        reg2.add(ParamDef(name="threshold1", type=float, default=100.0))
        reg2.load_values(data)
        assert reg2.get_value("threshold1") == 42.0
