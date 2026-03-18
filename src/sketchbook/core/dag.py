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

    def descendants(self, node_id: str) -> list[str]:
        """Return IDs of all nodes reachable downstream from node_id (BFS, excluding node_id)."""
        if node_id not in self._nodes:
            raise KeyError(f"No node '{node_id}' in DAG")
        result: list[str] = []
        seen: set[str] = {node_id}
        queue: deque[str] = deque([node_id])
        while queue:
            nid = queue.popleft()
            for from_id, to_id, _ in self._edges:
                if from_id == nid and to_id not in seen:
                    seen.add(to_id)
                    result.append(to_id)
                    queue.append(to_id)
        return result

    def validate(self) -> None:
        """Raise ValueError if any required input is not connected."""
        for node in self._nodes.values():
            for input_name, spec in node.step._inputs.items():
                if not spec.optional and input_name not in node._inputs:
                    raise ValueError(
                        f"Required input '{input_name}' of step '{node.id}' is not connected. "
                        f"Connected inputs: {list(node._inputs)}"
                    )

    def node(self, node_id: str) -> DAGNode:
        """Look up a node by ID."""
        if node_id not in self._nodes:
            raise KeyError(f"No node '{node_id}' in DAG")
        return self._nodes[node_id]

    def node_depths(self) -> dict[str, int]:
        """Return the depth (longest upstream path length) for each node."""
        depths: dict[str, int] = {}
        for node in self.topo_sort():
            if not node._inputs:
                depths[node.id] = 0
            else:
                depths[node.id] = max(depths[inp.id] for inp in node._inputs.values()) + 1
        return depths

    def connected_components(self) -> list[list[str]]:
        """Return node IDs grouped by connected component, each group in topological order."""
        adjacency: dict[str, set[str]] = {nid: set() for nid in self._nodes}
        for from_id, to_id, _ in self._edges:
            adjacency[from_id].add(to_id)
            adjacency[to_id].add(from_id)

        visited: set[str] = set()
        components: list[set[str]] = []
        for nid in self._nodes:
            if nid in visited:
                continue
            component: set[str] = set()
            queue = [nid]
            while queue:
                cur = queue.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                component.add(cur)
                queue.extend(adjacency[cur] - visited)
            components.append(component)

        topo_order = [n.id for n in self.topo_sort()]
        return [[nid for nid in topo_order if nid in component] for component in components]

    @property
    def nodes(self) -> dict[str, DAGNode]:
        """Return all nodes."""
        return dict(self._nodes)

    @property
    def edges(self) -> list[tuple[str, str, str]]:
        """Return all edges as (from_id, to_id, input_name) triples."""
        return list(self._edges)
