"""DAG graph, node types, topology sort, change propagation."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sketchbook.core.step import PipelineStep


class DAGNode:
    """Wraps a step instance, holds edges, stores cached output and workdir path."""

    def __init__(self, step: PipelineStep, node_id: str, workdir_path: str | None = None) -> None:
        self.step = step
        self.id = node_id
        self.workdir_path = workdir_path
        self._inputs: dict[str, DAGNode] = {}  # input_name -> source node
        self.output: Any = None

    def pipe(self, step_class: type, input_name: str = "image") -> DAGNode:
        """Connect this node's output to a new step and return the new node."""
        # Deferred: sketch wires this through the DAG
        raise NotImplementedError("pipe() must be called on a sketch-managed node")


class DAG:
    """Holds nodes and edges for a pipeline."""

    def __init__(self) -> None:
        self._nodes: dict[str, DAGNode] = {}
        self._edges: list[tuple[str, str, str]] = []  # (from_id, to_id, input_name)

    def add_node(self, node: DAGNode) -> None:
        """Register a node in the graph."""
        if node.id in self._nodes:
            raise ValueError(f"Node '{node.id}' already exists in the DAG")
        self._nodes[node.id] = node

    def connect(self, from_id: str, to_id: str, input_name: str = "image") -> None:
        """Add a directed edge from one node to another."""
        if from_id not in self._nodes:
            raise ValueError(f"Source node '{from_id}' not in DAG")
        if to_id not in self._nodes:
            raise ValueError(f"Target node '{to_id}' not in DAG")
        self._edges.append((from_id, to_id, input_name))
        self._nodes[to_id]._inputs[input_name] = self._nodes[from_id]

    def topo_sort(self) -> list[DAGNode]:
        """Return nodes in topological order."""
        in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}
        for _, to_id, _ in self._edges:
            in_degree[to_id] += 1

        queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        order: list[DAGNode] = []
        remaining_in_degree = dict(in_degree)

        while queue:
            nid = queue.popleft()
            order.append(self._nodes[nid])
            for from_id, to_id, _ in self._edges:
                if from_id == nid:
                    remaining_in_degree[to_id] -= 1
                    if remaining_in_degree[to_id] == 0:
                        queue.append(to_id)

        if len(order) != len(self._nodes):
            raise ValueError("DAG has a cycle")
        return order

    def node(self, node_id: str) -> DAGNode:
        """Look up a node by ID."""
        if node_id not in self._nodes:
            raise KeyError(f"No node '{node_id}' in DAG")
        return self._nodes[node_id]

    @property
    def nodes(self) -> dict[str, DAGNode]:
        """Return all nodes."""
        return dict(self._nodes)
