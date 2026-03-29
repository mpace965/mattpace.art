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
    return _execute_nodes(dag, subset=None)


def execute_partial(dag: DAG, start_node_ids: list[str]) -> ExecutionResult:
    """Re-execute start nodes and all their descendants in topological order.

    Nodes outside the subset are assumed to have valid cached outputs already.
    """
    subset: set[str] = set(start_node_ids)
    for nid in start_node_ids:
        subset.update(dag.descendants(nid))
    return _execute_nodes(dag, subset=subset)


def _execute_nodes(dag: DAG, subset: set[str] | None) -> ExecutionResult:
    """Run DAG nodes in topological order, optionally restricted to *subset*.

    When *subset* is None all nodes are executed. When *subset* is provided,
    nodes whose id is not in the set are skipped (their cached outputs remain).
    """
    result = ExecutionResult()
    failed_nodes: set[str] = set()
    partial = subset is not None

    for node in dag.topo_sort():
        if partial and node.id not in subset:
            continue

        upstream_failures = [src.id for src in node.source_nodes.values() if src.id in failed_nodes]
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
            params = node.step.param_values()
            suffix = " (partial)" if partial else ""
            log.debug(f"Executing node '{node.id}'{suffix}")
            node.output = node.step.process(inputs, params)
            result.executed.add(node.id)
            if node.workdir_path and node.output is not None:
                Path(node.workdir_path).write_bytes(node.output.to_bytes())
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
    sources = node.source_nodes
    for input_name, spec in node.step.input_specs.items():
        if input_name in sources:
            inputs[input_name] = sources[input_name].output
        elif spec.optional:
            inputs[input_name] = None
    return inputs


def _delete_workdir(node: DAGNode) -> None:
    """Delete the workdir output file for a failed node."""
    if node.workdir_path:
        path = Path(node.workdir_path)
        path.unlink(missing_ok=True)
        log.debug(f"Deleted stale output for '{node.id}': {path}")
