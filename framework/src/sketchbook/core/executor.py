"""execute_built / execute_partial_built — executor for BuiltDAG pipelines."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sketchbook.core.built_dag import BuiltDAG, BuiltNode
from sketchbook.core.introspect import find_ctx_param
from sketchbook.core.protocol import SketchValueProtocol


@dataclass
class ExecutionResult:
    """Result of running the full or partial DAG."""

    errors: dict[str, Exception] = field(default_factory=dict)
    executed: set[str] = field(default_factory=set)
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Return True if no nodes failed."""
        return not self.errors


log = logging.getLogger("sketchbook.executor")


def execute_built(
    dag: BuiltDAG,
    workdir: Path,
    mode: Literal["dev", "build"] = "dev",
) -> ExecutionResult:
    """Execute all nodes in *dag* in topological order, writing outputs to *workdir*.

    For each node:
    - If the result satisfies SketchValueProtocol, write
      ``<workdir>/<step_id>.<extension>``.
    - Otherwise write ``<workdir>/<step_id>.txt`` with the str() of the result.
    - On failure, delete any stale workdir file and propagate the failure to
      all downstream nodes.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    return _execute_nodes(dag, workdir, mode, subset=None)


def execute_partial_built(
    dag: BuiltDAG,
    start_ids: list[str],
    workdir: Path,
    mode: Literal["dev", "build"] = "dev",
) -> ExecutionResult:
    """Re-execute *start_ids* and all their descendants.

    Nodes outside the computed subset keep their cached outputs.
    """
    subset: set[str] = set(start_ids)
    for sid in start_ids:
        subset.update(dag.descendants(sid))
    workdir.mkdir(parents=True, exist_ok=True)
    return _execute_nodes(dag, workdir, mode, subset=subset)


def _execute_nodes(
    dag: BuiltDAG,
    workdir: Path,
    mode: Literal["dev", "build"],
    subset: set[str] | None,
) -> ExecutionResult:
    result = ExecutionResult()
    failed: set[str] = set()

    for node in dag.nodes_in_order():
        if subset is not None and node.step_id not in subset:
            continue

        # Check whether any upstream node failed.
        upstream_failures = [sid for sid in node.source_ids.values() if sid in failed]
        if upstream_failures:
            causes = "; ".join(f"{sid}: {result.errors[sid]}" for sid in upstream_failures)
            exc = RuntimeError(f"No output — upstream failure: {causes}")
            result.errors[node.step_id] = exc
            failed.add(node.step_id)
            node.output = None
            _delete_workdir_file(node, workdir)
            log.warning(f"Node '{node.step_id}' skipped due to upstream failure")
            continue

        try:
            inputs = {name: dag.nodes[sid].output for name, sid in node.source_ids.items()}
            kwargs = {**inputs, **node.param_values}
            if node.ctx is not None:
                ctx_param_name = find_ctx_param(node.fn)
                if ctx_param_name is not None:
                    kwargs[ctx_param_name] = node.ctx
            log.debug(f"Executing node '{node.step_id}'")
            t0 = time.perf_counter()
            value = node.fn(**kwargs)
            elapsed = time.perf_counter() - t0
            log.debug(f"Node '{node.step_id}' took {elapsed:.3f}s")
            node.output = value
            result.executed.add(node.step_id)
            result.timings[node.step_id] = elapsed

            if mode == "dev":
                if isinstance(value, SketchValueProtocol):
                    out_path = workdir / f"{node.step_id}.{value.extension}"
                    out_path.write_bytes(value.to_bytes(mode))
                    log.debug(f"Wrote '{node.step_id}' → {out_path}")
                elif value is not None:
                    out_path = workdir / f"{node.step_id}.txt"
                    out_path.write_bytes(str(value).encode())
                    log.debug(f"Wrote '{node.step_id}' → {out_path}")

        except Exception as exc:
            result.errors[node.step_id] = exc
            failed.add(node.step_id)
            node.output = None
            _delete_workdir_file(node, workdir)
            log.warning(f"Node '{node.step_id}' failed: {exc}")

    return result


def _delete_workdir_file(node: BuiltNode, workdir: Path) -> None:
    """Delete all workdir output files for a failed node (any extension)."""
    for path in workdir.glob(f"{node.step_id}.*"):
        path.unlink(missing_ok=True)
        log.debug(f"Deleted stale output for '{node.step_id}': {path}")
