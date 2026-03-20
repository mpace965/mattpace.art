"""Sketch base class with build() DSL."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from sketchbook.core.dag import DAG, DAGNode
from sketchbook.core.presets import PresetManager
from sketchbook.core.step import PipelineStep

log = logging.getLogger("sketchbook.sketch")


class _ManagedNode(DAGNode):
    """A DAGNode whose pipe() method is wired through a parent Sketch."""

    def __init__(self, step: PipelineStep, node_id: str, sketch: Sketch, **kwargs: Any) -> None:
        super().__init__(step, node_id, **kwargs)
        self._sketch = sketch

    def pipe(
        self,
        step_class: type[PipelineStep],
        input_name: str = "image",
        params: dict[str, dict] | None = None,
    ) -> _ManagedNode:
        """Connect this node's output to a new step instance."""
        return self._sketch._pipe(self, step_class, input_name, param_overrides=params)


class Sketch:
    """Base class for all sketches. Override build() to define the pipeline."""

    name: str = ""
    description: str = ""
    date: str = ""
    site_presets: list[str] | None = None  # None = all saved presets

    def __init__(self, sketch_dir: str | Path) -> None:
        self._sketch_dir = Path(sketch_dir)
        self._dag = DAG()
        self._workdir = self._sketch_dir / ".workdir"
        self._workdir.mkdir(parents=True, exist_ok=True)
        self._step_counts: dict[str, int] = {}
        self.build()
        self._preset_manager = PresetManager(self._sketch_dir / "presets")
        self._preset_manager.load_active(self._dag)

    @property
    def dag(self) -> DAG:
        """Return the built DAG."""
        return self._dag

    @property
    def sketch_dir(self) -> Path:
        """Return the sketch directory."""
        return self._sketch_dir

    @property
    def preset_manager(self) -> PresetManager:
        """Return the preset manager for this sketch."""
        return self._preset_manager

    def build(self) -> None:
        """Override to define the pipeline."""
        raise NotImplementedError(f"{type(self).__name__} must implement build()")

    def source(self, name: str, path: str) -> _ManagedNode:
        """Add a SourceFile node to the DAG."""
        from sketchbook.steps.source import SourceFile

        step = SourceFile(self._sketch_dir / path)
        node_id = f"source_{name}"
        workdir_path = self._workdir / f"{node_id}.png"
        node = _ManagedNode(step, node_id, self, workdir_path=str(workdir_path))
        self._dag.add_node(node)
        log.debug(f"Added source node '{node_id}' watching {self._sketch_dir / path}")
        return node

    def _next_id(self, step_class: type[PipelineStep]) -> str:
        """Return the next auto-generated node ID for step_class and advance the counter."""
        base_name = _step_id_base(step_class)
        count = self._step_counts.get(base_name, 0)
        self._step_counts[base_name] = count + 1
        return f"{base_name}_{count}"

    def _make_node(
        self,
        step_class: type[PipelineStep],
        node_id: str,
        param_overrides: dict[str, dict] | None = None,
    ) -> _ManagedNode:
        """Instantiate step_class, apply param overrides, create a workdir path, register in DAG."""
        step = step_class()
        if param_overrides:
            for param_name, fields in param_overrides.items():
                step._param_registry.override(param_name, **fields)
        workdir_path = self._workdir / f"{node_id}.png"
        node = _ManagedNode(step, node_id, self, workdir_path=str(workdir_path))
        self._dag.add_node(node)
        return node

    def _pipe(
        self,
        from_node: _ManagedNode,
        step_class: type[PipelineStep],
        input_name: str,
        param_overrides: dict[str, dict] | None = None,
    ) -> _ManagedNode:
        """Internal: instantiate step_class, add node, wire edge, apply param overrides."""
        node_id = self._next_id(step_class)
        node = self._make_node(step_class, node_id, param_overrides)
        self._dag.connect(from_node.id, node_id, input_name)
        log.debug(f"Wired {from_node.id} -> {node_id} via '{input_name}'")
        return node

    def output_bundle(self, node: _ManagedNode, bundle_name: str) -> _ManagedNode:
        """Add an OutputBundle node after the given node and return it.

        The builder scans for OutputBundle nodes with a matching bundle_name
        to determine what to bake and include in the output JSON.
        """
        from sketchbook.steps.output_bundle import OutputBundle

        node_id = self._next_id(OutputBundle)
        step = OutputBundle(bundle_name)
        workdir_path = self._workdir / f"{node_id}.png"
        managed = _ManagedNode(step, node_id, self, workdir_path=str(workdir_path))
        self._dag.add_node(managed)
        self._dag.connect(node.id, node_id, "image")
        log.debug(f"Wired {node.id} -> {node_id} via 'image' (bundle: {bundle_name!r})")
        return managed

    def add(
        self,
        step_class: type[PipelineStep],
        inputs: dict[str, _ManagedNode],
        id: str | None = None,
        params: dict[str, dict] | None = None,
    ) -> _ManagedNode:
        """Add a step with explicit named inputs.

        Args:
            step_class: The step class to instantiate.
            inputs: Mapping of input_name -> source node.
            id: Optional explicit node ID. Auto-generated if omitted.
            params: Optional param overrides (same format as pipe()).
        """
        node_id = self._next_id(step_class) if id is None else id
        node = self._make_node(step_class, node_id, params)
        for input_name, source_node in inputs.items():
            self._dag.connect(source_node.id, node_id, input_name)
        log.debug(f"Added step '{node_id}' with explicit inputs {list(inputs)}")
        return node


def _step_id_base(step_class: type) -> str:
    """Convert a class name to snake_case for use as a node ID prefix."""
    name = step_class.__name__
    # CamelCase -> snake_case
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
