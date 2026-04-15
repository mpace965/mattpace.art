"""Unit tests for SketchValueProtocol."""

from __future__ import annotations

from typing import Literal

from sketchbook.core.protocol import SketchValueProtocol


class _FullImpl:
    extension = "png"

    def to_bytes(self, mode: Literal["dev", "build"]) -> bytes:
        return b""

    def to_html(self, url: str) -> str:
        return f'<img src="{url}">'


class _NoHtml:
    extension = "png"

    def to_bytes(self, mode: Literal["dev", "build"]) -> bytes:
        return b""


class _NoToBytes:
    extension = "png"

    def to_html(self, url: str) -> str:
        return f'<img src="{url}">'


class _NoExtension:
    def to_bytes(self, mode: Literal["dev", "build"]) -> bytes:
        return b""


def test_full_impl_passes() -> None:
    """Object with extension + to_bytes + to_html satisfies the protocol."""
    assert isinstance(_FullImpl(), SketchValueProtocol)


def test_no_html_still_passes() -> None:
    """Object without to_html still satisfies the protocol (to_html is optional)."""
    assert isinstance(_NoHtml(), SketchValueProtocol)


def test_missing_to_bytes_fails() -> None:
    """Object without to_bytes does not satisfy the protocol."""
    assert not isinstance(_NoToBytes(), SketchValueProtocol)


def test_missing_extension_fails() -> None:
    """Object without extension does not satisfy the protocol."""
    assert not isinstance(_NoExtension(), SketchValueProtocol)
