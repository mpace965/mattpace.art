"""Acceptance test: Color param round-trips through preset JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sketchbook.core.dag import DAG, DAGNode
from sketchbook.core.params import Color
from sketchbook.core.presets import PresetManager
from sketchbook.core.step import PipelineStep
from sketchbook.core.types import Image


class Colorize(PipelineStep):
    """Tint an image with a solid color layer (test step)."""

    def setup(self) -> None:
        """Declare image input and color parameter."""
        self.add_input("image", Image)
        self.add_param("tint", Color, default=Color("#ff69b4"), label="Tint color")

    def process(self, inputs: dict[str, Any], params: dict[str, Any]) -> Image:
        """Return the input image (color conversion is not exercised here)."""
        return inputs["image"]


@pytest.fixture()
def color_dag(tmp_path: Path):
    """DAG with a Colorize step wired up."""
    from sketchbook.steps.source import SourceFile

    dag = DAG()
    source = SourceFile(tmp_path / "img.png")
    dag.add_node(DAGNode(source, "source"))
    step = Colorize()
    node = DAGNode(step, "colorize")
    dag.add_node(node)
    dag.connect("source", "colorize", "image")
    return dag, "colorize", "tint"


def test_color_preset_round_trip(tmp_path: Path, color_dag) -> None:
    """Save a Color param to a preset, reload it — registry value is a Color."""
    dag, node_id, param_name = color_dag
    node = dag.node(node_id)

    # Set a non-default color
    node.step._param_registry.set_value(param_name, Color("#1a2b3c"))

    pm = PresetManager(tmp_path / "presets")
    pm.save_preset("test", dag)

    # Verify the JSON contains a hex string, not a raw object
    data = json.loads((tmp_path / "presets" / "test.json").read_text())
    assert data[node_id][param_name] == "#1a2b3c"

    # Reset and reload — value should be restored as a Color instance
    node.step._param_registry.set_value(param_name, Color("#ffffff"))

    pm2 = PresetManager(tmp_path / "presets")
    pm2.load_preset("test", dag)

    restored = node.step._param_registry.get_value(param_name)
    assert isinstance(restored, Color)
    assert restored.r == 0x1A
    assert restored.g == 0x2B
    assert restored.b == 0x3C
