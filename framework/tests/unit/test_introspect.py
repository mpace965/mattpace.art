"""Unit tests for extract_inputs()."""

from __future__ import annotations

from sketchbook.core.decorators import SketchContext
from sketchbook.core.introspect import extract_inputs


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
