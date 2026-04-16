"""Increment 4 acceptance tests: v3 static site builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sketchbook.bundle.builder import build_bundle_fns
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import SketchContext, sketch, step
from tests.conftest import TestImage, make_test_image

# ---------------------------------------------------------------------------
# Test sketch: scale_factor + resize, SketchContext-driven, preset required
# ---------------------------------------------------------------------------


@step
def scale_factor(ctx: SketchContext) -> float:
    """Return 0.25 in dev, 1.0 in build."""
    return 0.25 if ctx.mode == "dev" else 1.0


@step
def resize(image: TestImage, scale: float) -> TestImage:
    """Return a TestImage annotated with the scale so we can verify mode."""
    tag = f"scale:{scale:.2f}:".encode()
    return TestImage(tag + image._data)


@sketch(date="2026-01-01")
def build_demo():
    """Sketch that produces different output in dev vs build."""
    img = source("assets/hello.png", loader=lambda p: TestImage.load(p))
    sc = scale_factor()
    result = resize(img, sc)
    output(result, "bundle", presets=["default"])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_fn_sketch_with_preset(tmp_path: Path) -> Path:
    """Sketch directory for build_demo with a 'default' preset saved."""
    sketch_dir = tmp_path / "build_demo"
    assets_dir = sketch_dir / "assets"
    assets_dir.mkdir(parents=True)
    make_test_image(assets_dir / "hello.png")

    presets_dir = sketch_dir / "presets"
    presets_dir.mkdir()
    (presets_dir / "default.json").write_text("{}")
    return sketch_dir


@pytest.fixture()
def tmp_output_dir(tmp_path: Path) -> Path:
    """Empty output directory for the builder."""
    out = tmp_path / "dist"
    out.mkdir()
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_produces_manifest_and_images(
    tmp_fn_sketch_with_preset: Path, tmp_output_dir: Path
) -> None:
    """build_bundle_fns writes manifest.json and a baked image for each preset."""
    sketches_dir = tmp_fn_sketch_with_preset.parent
    build_bundle_fns(
        sketch_fns={"build_demo": build_demo},
        sketches_dir=sketches_dir,
        output_dir=tmp_output_dir,
        bundle_name="bundle",
    )
    manifest_path = tmp_output_dir / "manifest.json"
    assert manifest_path.exists(), "manifest.json was not written"

    manifest = json.loads(manifest_path.read_text())
    assert len(manifest) == 1
    entry = manifest[0]
    assert entry["slug"] == "build-demo"
    assert len(entry["variants"]) == 1
    image_path = tmp_output_dir / entry["variants"][0]["image_path"]
    assert image_path.exists(), f"Baked image missing: {image_path}"
    assert image_path.stat().st_size > 0


def test_build_uses_build_mode_bytes(tmp_fn_sketch_with_preset: Path, tmp_output_dir: Path) -> None:
    """Baked images use to_bytes('build'), which differs from to_bytes('dev')."""
    sketches_dir = tmp_fn_sketch_with_preset.parent
    build_bundle_fns(
        sketch_fns={"build_demo": build_demo},
        sketches_dir=sketches_dir,
        output_dir=tmp_output_dir,
        bundle_name="bundle",
    )
    manifest = json.loads((tmp_output_dir / "manifest.json").read_text())
    image_path = tmp_output_dir / manifest[0]["variants"][0]["image_path"]
    built_bytes = image_path.read_bytes()

    assert built_bytes.startswith(b"mode:build:"), (
        f"Expected build-mode bytes, got: {built_bytes[:20]!r}"
    )


def test_sketch_context_mode_in_build(
    tmp_fn_sketch_with_preset: Path, tmp_output_dir: Path
) -> None:
    """Steps that declare SketchContext receive mode='build' — scale_factor returns 1.0."""
    sketches_dir = tmp_fn_sketch_with_preset.parent
    build_bundle_fns(
        sketch_fns={"build_demo": build_demo},
        sketches_dir=sketches_dir,
        output_dir=tmp_output_dir,
        bundle_name="bundle",
    )
    manifest = json.loads((tmp_output_dir / "manifest.json").read_text())
    image_path = tmp_output_dir / manifest[0]["variants"][0]["image_path"]
    built_bytes = image_path.read_bytes()

    assert b"scale:1.00:" in built_bytes, (
        f"Expected scale=1.0 (build mode), got: {built_bytes[:40]!r}"
    )
