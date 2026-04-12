"""Acceptance tests for execution profiles end-to-end."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from sketchbook.core.executor import execute
from sketchbook.core.profile import ExecutionProfile
from sketchbook.core.sketch import Sketch
from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_asset(sketch_dir: Path) -> None:
    """Write a minimal PNG asset so SourceFile can load something real."""
    import cv2

    assets = sketch_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(assets / "photo.png"), np.zeros((4, 4, 3), dtype=np.uint8))


_TINY_IMAGE = Image(np.zeros((4, 4, 3), dtype=np.uint8))


class _RecordingSketch(Sketch):
    """Sketch that records the profile passed to build()."""

    name = "recording"
    description = ""
    date = ""
    recorded_compress_level: int = -1

    def build(self, profile: ExecutionProfile) -> None:
        _RecordingSketch.recorded_compress_level = profile.compress_level
        self.source("photo", "assets/photo.png", loader=lambda _p: _TINY_IMAGE)


class _OverrideSketch(Sketch):
    """Sketch that overrides the 'build' profile with compress_level=9."""

    name = "override"
    description = ""
    date = ""
    recorded_compress_level: int = -1

    def execution_profiles(self) -> dict[str, ExecutionProfile]:
        return {"build": ExecutionProfile(draft_scale=1.0, compress_level=9)}

    def build(self, profile: ExecutionProfile) -> None:
        _OverrideSketch.recorded_compress_level = profile.compress_level
        self.source("photo", "assets/photo.png", loader=lambda _p: _TINY_IMAGE)


class _DevSketch(Sketch):
    """Sketch that records compress_level in dev mode."""

    name = "dev"
    description = ""
    date = ""
    recorded_compress_level: int = -1

    def build(self, profile: ExecutionProfile) -> None:
        _DevSketch.recorded_compress_level = profile.compress_level
        self.source("photo", "assets/photo.png", loader=lambda _p: _TINY_IMAGE)


# ---------------------------------------------------------------------------
# Acceptance scenario 1: profile reaches build()
# ---------------------------------------------------------------------------


def test_profile_reaches_build_in_build_mode(tmp_path: Path) -> None:
    """Framework 'build' default compress_level=9 should arrive in build()."""
    _make_asset(tmp_path)
    _RecordingSketch.recorded_compress_level = -1
    _RecordingSketch(tmp_path, mode="build")
    assert _RecordingSketch.recorded_compress_level == 9


# ---------------------------------------------------------------------------
# Acceptance scenario 2: sketch override is applied
# ---------------------------------------------------------------------------


def test_sketch_override_wins_in_build_mode(tmp_path: Path) -> None:
    """Sketch-level profile override should take precedence over framework default."""
    _make_asset(tmp_path)
    _OverrideSketch.recorded_compress_level = -1
    _OverrideSketch(tmp_path, mode="build")
    assert _OverrideSketch.recorded_compress_level == 9


# ---------------------------------------------------------------------------
# Acceptance scenario 3: OutputBundle stamps compress_level end-to-end
# ---------------------------------------------------------------------------


class _PassthroughStep(PipelineStep):
    def setup(self) -> None:
        self.add_input("image", Image)

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        return inputs["image"]


def test_output_bundle_stamps_compress_level(tmp_path: Path) -> None:
    """OutputBundle with compress_level=9 must produce different bytes than compress_level=0."""
    _make_asset(tmp_path)

    class _BundleSketch(Sketch):
        name = "bundle"
        description = ""
        date = ""

        def build(self, profile: ExecutionProfile) -> None:
            src = self.source("photo", "assets/photo.png", loader=lambda _p: _TINY_IMAGE)
            self.output_bundle(src, "main", compress_level=profile.compress_level)

    sketch_high = _BundleSketch(tmp_path, mode="build")
    result_high = execute(sketch_high.dag)
    assert result_high.ok

    bundle_node_id = [n for n in sketch_high.dag.nodes if "output_bundle" in n][0]
    bytes_compressed = sketch_high.dag.node(bundle_node_id).output.to_bytes()

    sketch_low = _BundleSketch(tmp_path, mode="dev")
    result_low = execute(sketch_low.dag)
    assert result_low.ok

    bytes_uncompressed = sketch_low.dag.node(bundle_node_id).output.to_bytes()

    assert bytes_compressed != bytes_uncompressed


# ---------------------------------------------------------------------------
# Acceptance scenario 4: dev mode uses dev profile
# ---------------------------------------------------------------------------


def test_dev_mode_uses_dev_profile(tmp_path: Path) -> None:
    """Default dev mode should yield compress_level=0."""
    _make_asset(tmp_path)
    _DevSketch.recorded_compress_level = -1
    _DevSketch(tmp_path)  # default mode="dev"
    assert _DevSketch.recorded_compress_level == 0
