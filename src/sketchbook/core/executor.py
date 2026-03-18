"""Pipeline execution engine — runs DAG nodes in topological order."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sketchbook.core.dag import DAG, DAGNode

log = logging.getLogger("sketchbook.executor")


@dataclass
class ExecutionResult:
    """Result of running the full or partial DAG."""

    errors: dict[str, Exception] = field(default_factory=dict)
    executed: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        """Return True if no nodes failed."""
        return not self.errors


def execute(dag: DAG) -> ExecutionResult:
    """Walk the DAG in topological order and run each step.

    Failures propagate: if a node fails, its output is cleared and downstream
    nodes that depend on it are also failed. Workdir files for failed nodes are
    deleted so the filesystem reflects the current pipeline state.
    """
    result = ExecutionResult()
    failed_nodes: set[str] = set()

    for node in dag.topo_sort():
        upstream_failures = [src.id for src in node._inputs.values() if src.id in failed_nodes]
        if upstream_failures:
            causes = "; ".join(f"{nid}: {result.errors[nid]}" for nid in upstream_failures)
            exc = RuntimeError(f"No output — {causes}")
            result.errors[node.id] = exc
            failed_nodes.add(node.id)
            node.output = None
            _delete_workdir(node)
            log.warning(str(exc))
            continue

        try:
            inputs = _gather_inputs(node)
            params = node.step._param_registry.values()
            log.debug(f"Executing node '{node.id}'")
            node.output = node.step.process(inputs, params)
            result.executed.add(node.id)
            if node.workdir_path and node.output is not None:
                node.output.save(node.workdir_path)
                log.debug(f"Wrote output for '{node.id}' to {node.workdir_path}")
        except Exception as exc:
            result.errors[node.id] = exc
            failed_nodes.add(node.id)
            node.output = None
            _delete_workdir(node)
            log.warning(f"Node '{node.id}' failed: {exc}")

    return result


def execute_partial(dag: DAG, start_node_ids: list[str]) -> ExecutionResult:
    """Re-execute start nodes and all their descendants in topological order.

    Nodes outside the subset are assumed to have valid cached outputs already.
    """
    subset: set[str] = set(start_node_ids)
    for nid in start_node_ids:
        subset.update(dag.descendants(nid))

    result = ExecutionResult()
    failed_nodes: set[str] = set()

    for node in dag.topo_sort():
        if node.id not in subset:
            continue

        upstream_failures = [src.id for src in node._inputs.values() if src.id in failed_nodes]
        if upstream_failures:
            causes = "; ".join(f"{nid}: {result.errors[nid]}" for nid in upstream_failures)
            exc = RuntimeError(f"No output — {causes}")
            result.errors[node.id] = exc
            failed_nodes.add(node.id)
            node.output = None
            _delete_workdir(node)
            log.warning(str(exc))
            continue

        try:
            inputs = _gather_inputs(node)
            params = node.step._param_registry.values()
            log.debug(f"Executing node '{node.id}' (partial)")
            node.output = node.step.process(inputs, params)
            result.executed.add(node.id)
            if node.workdir_path and node.output is not None:
                node.output.save(node.workdir_path)
                log.debug(f"Wrote output for '{node.id}' to {node.workdir_path}")
        except Exception as exc:
            result.errors[node.id] = exc
            failed_nodes.add(node.id)
            node.output = None
            _delete_workdir(node)
            log.warning(f"Node '{node.id}' failed: {exc}")

    return result


def _gather_inputs(node: DAGNode) -> dict[str, Any]:
    """Build the inputs dict for a node, passing None for missing optional inputs."""
    inputs: dict[str, Any] = {}
    for input_name, spec in node.step._inputs.items():
        if input_name in node._inputs:
            inputs[input_name] = node._inputs[input_name].output
        elif spec.optional:
            inputs[input_name] = None
    return inputs


def _delete_workdir(node: DAGNode) -> None:
    """Delete the workdir output file for a failed node."""
    if node.workdir_path:
        path = Path(node.workdir_path)
        path.unlink(missing_ok=True)
        log.debug(f"Deleted stale output for '{node.id}': {path}")
