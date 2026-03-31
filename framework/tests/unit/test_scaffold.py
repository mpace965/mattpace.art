"""Unit tests for sketchbook.scaffold."""

from __future__ import annotations

from sketchbook.scaffold import slug_to_class_name


class TestSlugToClassName:
    """slug_to_class_name converts kebab-case slugs to PascalCase class names."""

    def test_single_word(self) -> None:
        assert slug_to_class_name("cardboard") == "Cardboard"

    def test_hyphenated(self) -> None:
        assert slug_to_class_name("my-sketch") == "MySketch"

    def test_multiple_hyphens(self) -> None:
        assert slug_to_class_name("fence-torn-paper") == "FenceTornPaper"

    def test_already_single_capitalized(self) -> None:
        assert slug_to_class_name("hello") == "Hello"
