"""BuiltDAG and supporting types — the resolved, executable pipeline graph."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sketchbook.core.decorators import Param, SketchContext


@dataclass
class ParamSpec:
    """Schema entry for one tunable step parameter."""

    name: str
    type: type
    default: Any
    param: Param


@dataclass
class BuiltNode:
    """One resolved node in a BuiltDAG.

    ``source_ids`` maps input names to upstream step IDs.
    Execution outputs are stored in ``ExecutionResult.outputs``, not here.
    """

    step_id: str
    fn: Callable
    source_ids: dict[str, str] = field(default_factory=dict)
    param_schema: list[ParamSpec] = field(default_factory=list)
    param_values: dict[str, Any] = field(default_factory=dict)
    ctx: SketchContext | None = None


@dataclass
class BuiltDAG:
    """Fully resolved, topologically ordered pipeline graph.

    ``nodes`` maps step_id to BuiltNode in insertion (topo) order.
    ``source_paths`` lists (path, source_step_id) for the file watcher.
    ``output_nodes`` lists (step_id, bundle_name, presets) for output handling.
    """

    nodes: dict[str, BuiltNode] = field(default_factory=dict)
    source_paths: list[tuple[Path, str]] = field(default_factory=list)
    output_nodes: list[tuple[str, str, list[str] | None]] = field(default_factory=list)

    def nodes_in_order(self) -> list[BuiltNode]:
        """Return nodes in topological order.

        Order is guaranteed by wire_sketch, which inserts each node only after
        all its sources have already been inserted.
        """
        return list(self.nodes.values())

    def node_depths(self) -> dict[str, int]:
        """Return step_id → depth (longest path from a root node) for every node."""
        depths: dict[str, int] = {}
        for node in self.nodes_in_order():
            if not node.source_ids:
                depths[node.step_id] = 0
            else:
                depths[node.step_id] = max(depths[sid] for sid in node.source_ids.values()) + 1
        return depths

    def descendants(self, node_id: str) -> list[str]:
        """Return all step IDs that (transitively) depend on *node_id* via BFS."""
        result: list[str] = []
        queue: list[str] = [node_id]
        while queue:
            current = queue.pop(0)
            for nid, node in self.nodes.items():
                if current in node.source_ids.values() and nid not in result:
                    result.append(nid)
                    queue.append(nid)
        return result
