"""Unit tests for extract_inputs() and extract_params()."""

from __future__ import annotations

from typing import Annotated

from sketchbook.core.decorators import Param, SketchContext, step
from sketchbook.core.introspect import extract_inputs, extract_params


class _FakeImage:
    pass


def test_single_required_input() -> None:
    """A function with one typed input returns one non-optional InputSpec."""

    def f(image: _FakeImage) -> _FakeImage:
        return image

    specs = extract_inputs(f)
    assert len(specs) == 1
    assert specs[0].name == "image"
    assert specs[0].optional is False


def test_optional_input() -> None:
    """A parameter with T | None annotation and None default is optional."""

    def f(image: _FakeImage, mask: _FakeImage | None = None) -> _FakeImage:
        return image

    specs = extract_inputs(f)
    assert len(specs) == 2
    assert specs[1].name == "mask"
    assert specs[1].optional is True


def test_sketch_context_excluded() -> None:
    """Parameters annotated as SketchContext are excluded from the result."""

    def f(ctx: SketchContext, image: _FakeImage) -> _FakeImage:
        return image

    specs = extract_inputs(f)
    assert len(specs) == 1
    assert specs[0].name == "image"


def test_no_positional_args_returns_empty() -> None:
    """A function with no positional parameters returns an empty list."""

    def f() -> None:
        pass

    specs = extract_inputs(f)
    assert specs == []


def test_keyword_only_excluded() -> None:
    """Keyword-only parameters (after *) are excluded."""

    def f(image: _FakeImage, *, sigma: float = 1.0) -> _FakeImage:
        return image

    specs = extract_inputs(f)
    assert len(specs) == 1
    assert specs[0].name == "image"


def test_declaration_order_preserved() -> None:
    """InputSpecs are returned in parameter declaration order."""

    def f(a: _FakeImage, b: _FakeImage, c: _FakeImage | None = None) -> _FakeImage:
        return a

    specs = extract_inputs(f)
    assert [s.name for s in specs] == ["a", "b", "c"]


def test_optional_base_type_unwrapped() -> None:
    """The type field of an optional InputSpec is the inner type, not Optional."""

    def f(mask: _FakeImage | None = None) -> None:
        pass

    specs = extract_inputs(f)
    assert specs[0].type is _FakeImage


def test_works_with_step_decorated_fn() -> None:
    """extract_inputs unwraps @step and reads the original signature."""
    from sketchbook.core.decorators import step

    @step
    def process(image: _FakeImage) -> _FakeImage:
        return image

    specs = extract_inputs(process)
    assert len(specs) == 1
    assert specs[0].name == "image"


# ---------------------------------------------------------------------------
# extract_params tests
# ---------------------------------------------------------------------------


def test_annotated_int_param() -> None:
    """Annotated[int, Param(min=0, max=255)] keyword-only arg → ParamSpec."""

    def f(image, *, level: Annotated[int, Param(min=0, max=255)] = 128) -> None: ...

    specs = extract_params(f)
    assert len(specs) == 1
    assert specs[0].name == "level"
    assert specs[0].type is int
    assert specs[0].default == 128
    assert specs[0].param.min == 0
    assert specs[0].param.max == 255


def test_annotated_float_with_default() -> None:
    """Annotated[float, Param(...)] = 0.5 → default=0.5."""

    def f(*, sigma: Annotated[float, Param(min=0.0, max=5.0)] = 0.5) -> None: ...

    specs = extract_params(f)
    assert specs[0].default == 0.5


def test_bare_kwarg_not_a_param() -> None:
    """A keyword-only arg without Param annotation is excluded."""

    def f(*, count: int = 3) -> None: ...

    assert extract_params(f) == []


def test_sketch_context_kwarg_excluded() -> None:
    """SketchContext keyword-only arg is excluded from params."""

    def f(*, ctx: SketchContext) -> None: ...

    assert extract_params(f) == []


def test_optional_param_with_annotated() -> None:
    """T | None with Param annotation is a valid optional param."""

    def f(*, blur: Annotated[int, Param(min=0)] | None = None) -> None: ...

    specs = extract_params(f)
    assert len(specs) == 1


def test_works_with_step_decorated_fn_params() -> None:
    """extract_params unwraps @step and reads the original signature."""

    @step
    def proc(image, *, level: Annotated[int, Param(min=0)] = 5) -> None: ...

    specs = extract_params(proc)
    assert len(specs) == 1
