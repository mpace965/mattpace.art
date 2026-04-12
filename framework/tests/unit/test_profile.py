"""Unit tests for ExecutionProfile and ProfileRegistry."""

from __future__ import annotations

import logging
from dataclasses import FrozenInstanceError

import pytest

from sketchbook.core.profile import ExecutionProfile, ProfileRegistry

# ---------------------------------------------------------------------------
# ExecutionProfile
# ---------------------------------------------------------------------------


def test_execution_profile_is_frozen() -> None:
    """Mutating a field on a frozen ExecutionProfile must raise FrozenInstanceError."""
    profile = ExecutionProfile(draft_scale=1.0, compress_level=0)
    with pytest.raises(FrozenInstanceError):
        profile.draft_scale = 0.5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Framework defaults sanity checks
# ---------------------------------------------------------------------------


def test_framework_ships_dev_profile() -> None:
    """'dev' must be present in framework defaults."""
    assert "dev" in ProfileRegistry._FRAMEWORK_DEFAULTS


def test_framework_ships_build_profile() -> None:
    """'build' must be present in framework defaults."""
    assert "build" in ProfileRegistry._FRAMEWORK_DEFAULTS


# ---------------------------------------------------------------------------
# ProfileRegistry.resolve cascade
# ---------------------------------------------------------------------------


def test_resolve_sketch_override_wins(caplog: pytest.LogCaptureFixture) -> None:
    """Sketch provides 'dev'; registry returns it without warning."""
    dev_profile = ExecutionProfile(draft_scale=0.5, compress_level=3)
    registry = ProfileRegistry({"dev": dev_profile})
    with caplog.at_level(logging.WARNING, logger="sketchbook.profile"):
        result = registry.resolve("dev")
    assert result is dev_profile
    assert not caplog.records


def test_resolve_falls_back_to_framework_default_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Sketch has no 'dev'; framework has 'dev'; resolve warns and returns framework value."""
    registry = ProfileRegistry({})
    with caplog.at_level(logging.WARNING, logger="sketchbook.profile"):
        result = registry.resolve("dev")
    assert result == ProfileRegistry._FRAMEWORK_DEFAULTS["dev"]
    assert len(caplog.records) == 1
    assert "dev" in caplog.records[0].message


def test_resolve_unknown_mode_falls_back_to_base_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown mode 'foobar' falls back to 'base' and logs a warning."""
    registry = ProfileRegistry({})
    with caplog.at_level(logging.WARNING, logger="sketchbook.profile"):
        result = registry.resolve("foobar")
    assert result == ProfileRegistry._FRAMEWORK_DEFAULTS["base"]
    assert len(caplog.records) >= 1
    assert any("foobar" in r.message or "base" in r.message for r in caplog.records)


def test_resolve_hard_fails_if_base_missing() -> None:
    """Subclass with empty _FRAMEWORK_DEFAULTS raises RuntimeError when base is absent."""

    class _EmptyRegistry(ProfileRegistry):
        _FRAMEWORK_DEFAULTS: dict[str, ExecutionProfile] = {}

    registry = _EmptyRegistry({})
    with pytest.raises(RuntimeError):
        registry.resolve("unknown_mode")
