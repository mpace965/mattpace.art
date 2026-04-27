"""Unit tests for ConnectionManager — broadcast, dump_initial_state, broadcast_results."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from sketchbook.core.built_dag import BuiltDAG, BuiltNode
from sketchbook.core.executor import ExecutionResult
from sketchbook.server.connection_manager import ConnectionManager, _is_cascaded

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dag(step_id: str = "step_a", output: Any = None) -> BuiltDAG:
    dag = BuiltDAG()
    node = BuiltNode(step_id=step_id, fn=lambda: None, output=output)
    dag.nodes[step_id] = node
    return dag


def _make_ws(messages: list[str] | None = None) -> MagicMock:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.send_text.side_effect = None
    return ws


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _is_cascaded
# ---------------------------------------------------------------------------


def test_is_cascaded_true_for_upstream_failure() -> None:
    exc = RuntimeError("No output — upstream failure in step_a")
    assert _is_cascaded(exc) is True


def test_is_cascaded_false_for_other_errors() -> None:
    assert _is_cascaded(ValueError("bad")) is False
    assert _is_cascaded(RuntimeError("something else")) is False


# ---------------------------------------------------------------------------
# add / discard / connections
# ---------------------------------------------------------------------------


def test_add_registers_connection() -> None:
    mgr = ConnectionManager()
    ws = _make_ws()
    mgr.add("sketch_a", ws)
    assert ws in mgr.connections["sketch_a"]


def test_discard_removes_connection() -> None:
    mgr = ConnectionManager()
    ws = _make_ws()
    mgr.add("sketch_a", ws)
    mgr.discard("sketch_a", ws)
    assert ws not in mgr.connections["sketch_a"]


# ---------------------------------------------------------------------------
# broadcast
# ---------------------------------------------------------------------------


def test_broadcast_sends_to_all_connections() -> None:
    mgr = ConnectionManager()
    ws1, ws2 = _make_ws(), _make_ws()
    mgr.add("s", ws1)
    mgr.add("s", ws2)
    _run(mgr.broadcast("s", {"type": "ping"}))
    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()


def test_broadcast_removes_dead_connections() -> None:
    mgr = ConnectionManager()
    dead_ws = _make_ws()
    dead_ws.send_text.side_effect = RuntimeError("closed")
    mgr.add("s", dead_ws)
    _run(mgr.broadcast("s", {"type": "ping"}))
    assert dead_ws not in mgr.connections["s"]


def test_broadcast_is_no_op_for_no_connections() -> None:
    mgr = ConnectionManager()
    _run(mgr.broadcast("nobody", {"type": "ping"}))  # must not raise


# ---------------------------------------------------------------------------
# broadcast_results
# ---------------------------------------------------------------------------


def test_broadcast_results_sends_step_updated_for_executed_node() -> None:
    """broadcast_results emits step_updated when a node ran successfully."""
    import os
    import tempfile

    from tests.conftest import TestImage, make_test_image

    # Use a minimal TestImage-like output that satisfies SketchValueProtocol.
    # TestImage implements the protocol; we just need a real instance.
    # Create a temp file for the make_test_image helper.
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = Path(f.name)
    try:
        make_test_image(tmp)
        output = TestImage.load(tmp)
    finally:
        os.unlink(tmp)

    dag = _make_dag("step_a", output=output)
    result = ExecutionResult(
        executed={"step_a"},
        errors={},
        timings={"step_a": 0.1},
    )
    mgr = ConnectionManager()
    ws = _make_ws()
    mgr.add("sketch_a", ws)
    _run(mgr.broadcast_results("sketch_a", dag, result))

    calls = [json.loads(c.args[0]) for c in ws.send_text.await_args_list]
    assert any(m["type"] == "step_updated" and m["step_id"] == "step_a" for m in calls)


def test_broadcast_results_sends_step_error_for_non_cascaded_error() -> None:
    dag = _make_dag("step_a")
    result = ExecutionResult(
        executed=set(),
        errors={"step_a": ValueError("oops")},
        timings={},
    )
    mgr = ConnectionManager()
    ws = _make_ws()
    mgr.add("s", ws)
    _run(mgr.broadcast_results("s", dag, result))

    calls = [json.loads(c.args[0]) for c in ws.send_text.await_args_list]
    assert any(m["type"] == "step_error" for m in calls)


def test_broadcast_results_sends_step_blocked_for_cascaded_error() -> None:
    dag = _make_dag("step_a")
    cascade = RuntimeError("No output — upstream failure in parent_step")
    result = ExecutionResult(
        executed=set(),
        errors={"step_a": cascade},
        timings={},
    )
    mgr = ConnectionManager()
    ws = _make_ws()
    mgr.add("s", ws)
    _run(mgr.broadcast_results("s", dag, result))

    calls = [json.loads(c.args[0]) for c in ws.send_text.await_args_list]
    assert any(m["type"] == "step_blocked" for m in calls)


# ---------------------------------------------------------------------------
# dump_initial_state
# ---------------------------------------------------------------------------


def test_dump_initial_state_sends_step_updated_for_existing_output_file(
    tmp_path: Path,
) -> None:
    """dump_initial_state sends step_updated only when the workdir file exists."""
    from tests.conftest import TestImage, make_test_image

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    make_test_image(workdir / "step_a.png")

    output_val = TestImage.load(workdir / "step_a.png")
    dag = _make_dag("step_a", output=output_val)

    ws = _make_ws()
    mgr = ConnectionManager()
    _run(mgr.dump_initial_state(ws, "s", dag, workdir, last_result=None))

    calls = [json.loads(c.args[0]) for c in ws.send_text.await_args_list]
    assert any(m["type"] == "step_updated" and m["step_id"] == "step_a" for m in calls)


def test_dump_initial_state_skips_step_updated_when_file_missing(
    tmp_path: Path,
) -> None:
    """dump_initial_state skips step_updated when workdir file does not exist."""
    import os
    import tempfile

    from tests.conftest import TestImage, make_test_image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = Path(f.name)
    make_test_image(tmp)
    output_val = TestImage.load(tmp)
    os.unlink(tmp)

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    # File is NOT in workdir

    dag = _make_dag("step_a", output=output_val)
    ws = _make_ws()
    mgr = ConnectionManager()
    _run(mgr.dump_initial_state(ws, "s", dag, workdir, last_result=None))

    ws.send_text.assert_not_awaited()


def test_dump_initial_state_sends_step_error_for_last_result_error(
    tmp_path: Path,
) -> None:
    """dump_initial_state sends step_error when last_result has an error for that node."""
    dag = _make_dag("step_a", output=None)
    last_result = ExecutionResult(
        executed=set(),
        errors={"step_a": ValueError("bad step")},
        timings={},
    )
    ws = _make_ws()
    mgr = ConnectionManager()
    _run(mgr.dump_initial_state(ws, "s", dag, tmp_path, last_result=last_result))

    calls = [json.loads(c.args[0]) for c in ws.send_text.await_args_list]
    assert any(m["type"] == "step_error" and m["step_id"] == "step_a" for m in calls)
