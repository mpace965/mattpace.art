"""Unit tests for SketchValueProtocol."""

from __future__ import annotations

from typing import Literal

from sketchbook.core.protocol import SketchValueProtocol, output_kind


class _FullImpl:
    extension = "png"
    kind = "image"

    def to_bytes(self, mode: Literal["dev", "build"]) -> bytes:
        return b""

    def to_html(self, url: str) -> str:
        return f'<img src="{url}">'


class _NoHtml:
    extension = "png"
    kind = "image"

    def to_bytes(self, mode: Literal["dev", "build"]) -> bytes:
        return b""


class _NoToBytes:
    extension = "png"
    kind = "image"

    def to_html(self, url: str) -> str:
        return f'<img src="{url}">'


class _NoExtension:
    kind = "image"

    def to_bytes(self, mode: Literal["dev", "build"]) -> bytes:
        return b""


def test_full_impl_passes() -> None:
    """Object with extension + kind + to_bytes satisfies the protocol."""
    assert isinstance(_FullImpl(), SketchValueProtocol)


def test_no_html_still_passes() -> None:
    """Object without to_html still satisfies the protocol (to_html is not required)."""
    assert isinstance(_NoHtml(), SketchValueProtocol)


def test_missing_to_bytes_fails() -> None:
    """Object without to_bytes does not satisfy the protocol."""
    assert not isinstance(_NoToBytes(), SketchValueProtocol)


def test_missing_extension_fails() -> None:
    """Object without extension does not satisfy the protocol."""
    assert not isinstance(_NoExtension(), SketchValueProtocol)


def test_output_kind_reads_from_protocol() -> None:
    """output_kind returns value.kind for protocol instances."""
    assert output_kind(_FullImpl()) == "image"


def test_output_kind_falls_back_to_text() -> None:
    """output_kind returns 'text' for plain Python values."""
    assert output_kind(42) == "text"
    assert output_kind(3.14) == "text"
    assert output_kind("hello") == "text"
