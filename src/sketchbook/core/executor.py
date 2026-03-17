"""Pipeline execution engine — runs DAG nodes in topological order."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from sketchbook.core.dag import DAG, DAGNode

log = logging.getLogger("sketchbook.executor")


@dataclass
class ExecutionResult:
    """Result of running the full DAG."""

    errors: dict[str, Exception] = field(default_factory=dict)

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
        # Fail downstream of any failed upstream
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
            inputs = {name: upstream.output for name, upstream in node._inputs.items()}
            log.debug(f"Executing node '{node.id}'")
            node.output = node.step.process(inputs, {})
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


def _delete_workdir(node: DAGNode) -> None:
    """Delete the workdir output file for a failed node."""
    if node.workdir_path:
        path = Path(node.workdir_path)
        path.unlink(missing_ok=True)
        log.debug(f"Deleted stale output for '{node.id}': {path}")
