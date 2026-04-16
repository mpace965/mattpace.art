"""Unit tests for build_bundle_fns."""

from __future__ import annotations

import json
from pathlib import Path

from sketchbook.bundle.builder import build_bundle_fns
from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import sketch, step
from tests.conftest import TestImage, make_test_image

# ---------------------------------------------------------------------------
# Shared step helpers
# ---------------------------------------------------------------------------


@step
def _passthrough_b(image: TestImage) -> TestImage:
    """Passthrough for builder unit tests."""
    return image


# ---------------------------------------------------------------------------
# Minimal test sketches (no output, no presets, preset filter)
# ---------------------------------------------------------------------------


@sketch(date="2026-01-01")
def _no_output():
    """Sketch that declares no output node."""
    img = source("assets/img.png", TestImage.load)
    _passthrough_b(img)
    # No output() call → dag.output_nodes is empty


@sketch(date="2026-02-01")
def _with_bundle():
    """Sketch with an output node but no presets saved on disk."""
    img = source("assets/img.png", TestImage.load)
    out = _passthrough_b(img)
    output(out, "bundle")


@sketch(date="2026-03-01")
def _preset_filter():
    """Sketch that restricts the build to the 'default' preset only."""
    img = source("assets/img.png", TestImage.load)
    out = _passthrough_b(img)
    output(out, "bundle", presets=["default"])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_sketch_dir(base: Path, sketch_key: str) -> Path:
    """Create a sketch directory with an asset file."""
    sketch_dir = base / sketch_key
    assets = sketch_dir / "assets"
    assets.mkdir(parents=True)
    make_test_image(assets / "img.png")
    return sketch_dir


def _add_preset(sketch_dir: Path, name: str) -> None:
    """Write an empty preset JSON file to the sketch's presets directory."""
    presets = sketch_dir / "presets"
    presets.mkdir(exist_ok=True)
    (presets / f"{name}.json").write_text("{}")


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------


def test_skip_sketch_with_no_output_nodes(tmp_path: Path) -> None:
    """build_bundle_fns skips sketches that have no output nodes for the bundle."""
    sketch_dir = _make_sketch_dir(tmp_path, "_no_output")
    _add_preset(sketch_dir, "default")

    output_dir = tmp_path / "dist"
    output_dir.mkdir()

    build_bundle_fns(
        sketch_fns={"_no_output": _no_output},
        sketches_dir=tmp_path,
        output_dir=output_dir,
        bundle_name="bundle",
    )

    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert manifest == []


def test_skip_sketch_with_no_presets(tmp_path: Path) -> None:
    """build_bundle_fns skips sketches that have no saved presets."""
    _make_sketch_dir(tmp_path, "_with_bundle")
    # No preset files written — presets dir does not even exist.

    output_dir = tmp_path / "dist"
    output_dir.mkdir()

    build_bundle_fns(
        sketch_fns={"_with_bundle": _with_bundle},
        sketches_dir=tmp_path,
        output_dir=output_dir,
        bundle_name="bundle",
    )

    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert manifest == []


# ---------------------------------------------------------------------------
# Preset filter
# ---------------------------------------------------------------------------


def test_preset_filter_honoured(tmp_path: Path) -> None:
    """output(presets=['default']) restricts which presets are built."""
    sketch_dir = _make_sketch_dir(tmp_path, "_preset_filter")
    _add_preset(sketch_dir, "default")
    _add_preset(sketch_dir, "alternative")

    output_dir = tmp_path / "dist"
    output_dir.mkdir()

    build_bundle_fns(
        sketch_fns={"_preset_filter": _preset_filter},
        sketches_dir=tmp_path,
        output_dir=output_dir,
        bundle_name="bundle",
        workers=1,
    )

    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert len(manifest) == 1
    variants = manifest[0]["variants"]
    variant_names = [v["name"] for v in variants]
    assert variant_names == ["default"]
    assert "alternative" not in variant_names


# ---------------------------------------------------------------------------
# Parallel execution and manifest structure
# ---------------------------------------------------------------------------


def test_parallel_execution_produces_correct_outputs(tmp_path: Path) -> None:
    """workers=1 sequential execution produces image files and a correct manifest."""
    sketch_dir = _make_sketch_dir(tmp_path, "_with_bundle")
    _add_preset(sketch_dir, "default")
    _add_preset(sketch_dir, "vivid")

    output_dir = tmp_path / "dist"
    output_dir.mkdir()

    build_bundle_fns(
        sketch_fns={"_with_bundle": _with_bundle},
        sketches_dir=tmp_path,
        output_dir=output_dir,
        bundle_name="bundle",
        workers=1,
    )

    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert len(manifest) == 1
    assert len(manifest[0]["variants"]) == 2
    for variant in manifest[0]["variants"]:
        image_path = output_dir / variant["image_path"]
        assert image_path.exists(), f"Missing image: {image_path}"
        assert image_path.stat().st_size > 0


def test_manifest_slug_is_kebab_cased(tmp_path: Path) -> None:
    """Manifest slug is kebab-cased from the sketch_fns dict key."""
    sketch_dir = _make_sketch_dir(tmp_path, "_with_bundle")
    _add_preset(sketch_dir, "default")

    output_dir = tmp_path / "dist"
    output_dir.mkdir()

    build_bundle_fns(
        sketch_fns={"_with_bundle": _with_bundle},
        sketches_dir=tmp_path,
        output_dir=output_dir,
        bundle_name="bundle",
        workers=1,
    )

    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert manifest[0]["slug"] == "-with-bundle"


def test_manifest_reads_sketch_meta(tmp_path: Path) -> None:
    """Manifest name, description, date come from fn.__sketch_meta__."""
    sketch_dir = _make_sketch_dir(tmp_path, "_with_bundle")
    _add_preset(sketch_dir, "default")

    output_dir = tmp_path / "dist"
    output_dir.mkdir()

    build_bundle_fns(
        sketch_fns={"_with_bundle": _with_bundle},
        sketches_dir=tmp_path,
        output_dir=output_dir,
        bundle_name="bundle",
        workers=1,
    )

    manifest = json.loads((output_dir / "manifest.json").read_text())
    entry = manifest[0]
    assert entry["name"] == "_with_bundle"
    assert entry["description"] == "Sketch with an output node but no presets saved on disk."
    assert entry["date"] == "2026-02-01"
