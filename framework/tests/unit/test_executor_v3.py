"""Unit tests for execute_built() and execute_partial_built()."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from sketchbook.core.built_dag import BuiltDAG, BuiltNode
from sketchbook.core.decorators import SketchContext
from sketchbook.core.executor import execute_built, execute_partial_built
from sketchbook.core.protocol import SketchValueProtocol
from tests.conftest import TestImage

# ---------------------------------------------------------------------------
# Minimal SketchValueProtocol implementation
# ---------------------------------------------------------------------------


class _Img:
    extension = "png"
    kind = "image"

    def __init__(self, data: bytes = b"\x89PNG") -> None:
        self._data = data

    def to_bytes(self, mode: Literal["dev", "build"]) -> bytes:
        return self._data

    def to_html(self, url: str) -> str:
        return f'<img src="{url}">'


assert isinstance(_Img(), SketchValueProtocol)


# ---------------------------------------------------------------------------
# DAG builder helpers
# ---------------------------------------------------------------------------


def _source_node(step_id: str, data: bytes = b"src") -> BuiltNode:
    img = _Img(data)
    return BuiltNode(step_id=step_id, fn=lambda: img, source_ids={})


def _passthrough_node(step_id: str, upstream_id: str) -> BuiltNode:
    return BuiltNode(
        step_id=step_id,
        fn=lambda image: image,
        source_ids={"image": upstream_id},
    )


def _failing_node(step_id: str, upstream_id: str) -> BuiltNode:
    def _fail(image: _Img) -> _Img:
        raise RuntimeError("deliberate failure")

    return BuiltNode(step_id=step_id, fn=_fail, source_ids={"image": upstream_id})


def _primitive_node(step_id: str, upstream_id: str) -> BuiltNode:
    """Node that returns a plain string (not SketchValueProtocol)."""
    return BuiltNode(
        step_id=step_id,
        fn=lambda image: "hello world",
        source_ids={"image": upstream_id},
    )


def _two_node_dag() -> BuiltDAG:
    """source_img → pass_img."""
    dag = BuiltDAG()
    dag.nodes["source_img"] = _source_node("source_img")
    dag.nodes["pass_img"] = _passthrough_node("pass_img", "source_img")
    return dag


# ---------------------------------------------------------------------------
# execute_built — basic
# ---------------------------------------------------------------------------


def test_full_execution_writes_workdir_files(tmp_path: Path) -> None:
    """execute_built writes a file per executed node to workdir."""
    dag = _two_node_dag()
    result = execute_built(dag, tmp_path)

    assert result.ok
    assert "source_img" in result.executed
    assert "pass_img" in result.executed
    assert (tmp_path / "source_img.png").exists()
    assert (tmp_path / "pass_img.png").exists()


def test_protocol_value_uses_to_bytes(tmp_path: Path) -> None:
    """A SketchValueProtocol result writes <step_id>.<extension>."""
    dag = BuiltDAG()
    dag.nodes["src"] = BuiltNode(step_id="src", fn=lambda: _Img(b"custom_bytes"), source_ids={})

    execute_built(dag, tmp_path, mode="dev")

    out = tmp_path / "src.png"
    assert out.exists()
    assert out.read_bytes() == b"custom_bytes"


def test_primitive_value_writes_txt(tmp_path: Path) -> None:
    """A non-protocol return value is written as .txt."""
    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["text"] = _primitive_node("text", "src")

    execute_built(dag, tmp_path)

    out = tmp_path / "text.txt"
    assert out.exists()
    assert out.read_bytes() == b"hello world"


def test_upstream_failure_propagates(tmp_path: Path) -> None:
    """A failed node marks all downstream nodes as failed too."""
    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["bad"] = _failing_node("bad", "src")
    dag.nodes["down"] = _passthrough_node("down", "bad")

    result = execute_built(dag, tmp_path)

    assert not result.ok
    assert "bad" in result.errors
    assert "down" in result.errors
    assert "down" not in result.executed


def test_failed_node_workdir_file_deleted(tmp_path: Path) -> None:
    """After a node failure, any stale workdir file for that node is removed."""
    # Pre-create a stale file
    stale = tmp_path / "bad.png"
    stale.write_bytes(b"stale")

    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["bad"] = _failing_node("bad", "src")

    execute_built(dag, tmp_path)

    assert not stale.exists()


def test_workdir_created_if_missing(tmp_path: Path) -> None:
    """execute_built creates workdir if it does not exist yet."""
    workdir = tmp_path / "new_workdir"
    assert not workdir.exists()

    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    execute_built(dag, workdir)

    assert workdir.exists()


# ---------------------------------------------------------------------------
# execute_partial_built
# ---------------------------------------------------------------------------


def test_partial_only_reruns_start_and_descendants(tmp_path: Path) -> None:
    """execute_partial_built re-executes only the start node and descendants."""
    dag = _two_node_dag()

    prior = execute_built(dag, tmp_path)

    result = execute_partial_built(dag, ["source_img"], tmp_path, prior=prior)

    assert "source_img" in result.executed
    assert "pass_img" in result.executed


def test_partial_skips_unrelated_nodes(tmp_path: Path) -> None:
    """execute_partial_built skips nodes outside the affected subgraph."""
    dag = BuiltDAG()
    dag.nodes["src_a"] = _source_node("src_a", b"a")
    dag.nodes["src_b"] = _source_node("src_b", b"b")
    dag.nodes["from_a"] = _passthrough_node("from_a", "src_a")
    dag.nodes["from_b"] = _passthrough_node("from_b", "src_b")

    prior = execute_built(dag, tmp_path)

    # Only re-execute from src_b.
    result = execute_partial_built(dag, ["src_b"], tmp_path, prior=prior)

    assert "src_b" in result.executed
    assert "from_b" in result.executed
    assert "src_a" not in result.executed
    assert "from_a" not in result.executed


# ---------------------------------------------------------------------------
# param_values and ctx injection
# ---------------------------------------------------------------------------


def test_param_values_passed_as_kwargs(tmp_path: Path) -> None:
    """param_values are passed as keyword args to the step fn."""
    received: dict[str, object] = {}

    def proc(image: _Img, *, level: int = 128) -> _Img:
        received["level"] = level
        return image

    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["proc"] = BuiltNode(
        step_id="proc",
        fn=proc,
        source_ids={"image": "src"},
        param_values={"level": 64},
    )

    execute_built(dag, tmp_path)
    assert received["level"] == 64


def test_ctx_injected_when_declared(tmp_path: Path) -> None:
    """SketchContext is injected if the node has ctx set and fn declares it."""
    received: dict[str, object] = {}

    def proc(image: _Img, ctx: SketchContext) -> _Img:
        received["mode"] = ctx.mode
        return image

    ctx = SketchContext(mode="build")
    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["proc"] = BuiltNode(
        step_id="proc",
        fn=proc,
        source_ids={"image": "src"},
        ctx=ctx,
    )

    execute_built(dag, tmp_path)
    assert received["mode"] == "build"


def test_ctx_not_injected_when_none(tmp_path: Path) -> None:
    """No ctx injection when node.ctx is None."""
    received: dict[str, object] = {}

    def proc(image: _Img) -> _Img:
        received["called"] = True
        return image

    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["proc"] = BuiltNode(
        step_id="proc",
        fn=proc,
        source_ids={"image": "src"},
        ctx=None,
    )

    execute_built(dag, tmp_path)
    assert received.get("called") is True


# ---------------------------------------------------------------------------
# Increment 4: mode-aware to_bytes, ctx injection in build mode, no-input ctx step
# ---------------------------------------------------------------------------


def test_to_bytes_mode_distinguishes_dev_build() -> None:
    """TestImage.to_bytes('dev') and to_bytes('build') must return different bytes."""
    img = TestImage(b"\x00" * 64)
    assert img.to_bytes("dev") != img.to_bytes("build")


def test_execute_built_build_mode_no_disk_writes(tmp_path: Path) -> None:
    """mode='build' skips all disk writes — outputs are kept in memory only."""
    dag = BuiltDAG()
    dag.nodes["src"] = BuiltNode(
        step_id="src",
        fn=lambda: TestImage(b"data"),
        source_ids={},
    )

    execute_built(dag, tmp_path, mode="build")

    assert not any(tmp_path.iterdir()), "build mode must not write any files to workdir"
    assert dag.nodes["src"].output is not None, "output must be stored in memory"
    assert dag.nodes["src"].output.to_bytes("build").startswith(b"mode:build:")


def test_ctx_mode_is_build_during_build_execution(tmp_path: Path) -> None:
    """Steps that declare SketchContext receive mode='build' when node.ctx.mode == 'build'."""
    received: dict[str, object] = {}

    def step_with_ctx(image: _Img, ctx: SketchContext) -> _Img:
        received["mode"] = ctx.mode
        return image

    ctx = SketchContext(mode="build")
    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["step_with_ctx"] = BuiltNode(
        step_id="step_with_ctx",
        fn=step_with_ctx,
        source_ids={"image": "src"},
        ctx=ctx,
    )

    execute_built(dag, tmp_path, mode="build")

    assert received["mode"] == "build"


def test_no_input_step_with_ctx_executes_correctly(tmp_path: Path) -> None:
    """scale_factor()-style step (zero inputs, ctx only) produces output and flows downstream."""
    received: dict[str, object] = {}

    def scale_factor(ctx: SketchContext) -> float:
        received["mode"] = ctx.mode
        return 1.0

    ctx = SketchContext(mode="build")
    dag = BuiltDAG()
    dag.nodes["scale_factor"] = BuiltNode(
        step_id="scale_factor",
        fn=scale_factor,
        source_ids={},
        ctx=ctx,
    )

    result = execute_built(dag, tmp_path)
    assert result.ok
    assert received["mode"] == "build"
    assert dag.nodes["scale_factor"].output == 1.0


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------


def test_executed_nodes_have_timings(tmp_path: Path) -> None:
    """Every executed node has a non-negative float in result.timings."""
    dag = _two_node_dag()
    result = execute_built(dag, tmp_path)

    assert "source_img" in result.timings
    assert "pass_img" in result.timings
    assert result.timings["source_img"] >= 0.0
    assert result.timings["pass_img"] >= 0.0


def test_failed_nodes_not_in_timings(tmp_path: Path) -> None:
    """Nodes that raise do not appear in result.timings."""
    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["bad"] = _failing_node("bad", "src")

    result = execute_built(dag, tmp_path)

    assert "src" in result.timings
    assert "bad" not in result.timings


def test_skipped_nodes_not_in_timings(tmp_path: Path) -> None:
    """Nodes skipped due to upstream failure do not appear in result.timings."""
    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["bad"] = _failing_node("bad", "src")
    dag.nodes["down"] = _passthrough_node("down", "bad")

    result = execute_built(dag, tmp_path)

    assert "down" not in result.timings


def test_partial_execution_timings_only_for_rerun_nodes(tmp_path: Path) -> None:
    """execute_partial_built timings only cover re-executed nodes, not cached ones."""
    dag = BuiltDAG()
    dag.nodes["src_a"] = _source_node("src_a", b"a")
    dag.nodes["src_b"] = _source_node("src_b", b"b")
    dag.nodes["from_a"] = _passthrough_node("from_a", "src_a")
    dag.nodes["from_b"] = _passthrough_node("from_b", "src_b")

    prior = execute_built(dag, tmp_path)
    result = execute_partial_built(dag, ["src_b"], tmp_path, prior=prior)

    assert "src_b" in result.timings
    assert "from_b" in result.timings
    assert "src_a" not in result.timings
    assert "from_a" not in result.timings


# ---------------------------------------------------------------------------
# outputs dict on ExecutionResult
# ---------------------------------------------------------------------------


def test_full_execution_outputs_all_successful_nodes(tmp_path: Path) -> None:
    """execute_built populates result.outputs for every successfully-executed node."""
    dag = _two_node_dag()
    result = execute_built(dag, tmp_path)

    assert "source_img" in result.outputs
    assert "pass_img" in result.outputs
    assert isinstance(result.outputs["source_img"], _Img)
    assert isinstance(result.outputs["pass_img"], _Img)


def test_failed_node_absent_from_outputs(tmp_path: Path) -> None:
    """A node that raises must not appear in result.outputs."""
    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["bad"] = _failing_node("bad", "src")

    result = execute_built(dag, tmp_path)

    assert "src" in result.outputs
    assert "bad" not in result.outputs


def test_blocked_downstream_node_absent_from_outputs(tmp_path: Path) -> None:
    """Downstream nodes blocked by upstream failure must not appear in result.outputs."""
    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["bad"] = _failing_node("bad", "src")
    dag.nodes["down"] = _passthrough_node("down", "bad")

    result = execute_built(dag, tmp_path)

    assert "down" not in result.outputs


def test_partial_execution_outputs_rerun_nodes_win_over_prior(tmp_path: Path) -> None:
    """Newly-executed outputs win over prior values on collision."""
    call_count = [0]

    def counting_source() -> _Img:
        call_count[0] += 1
        return _Img(f"call-{call_count[0]}".encode())

    dag = BuiltDAG()
    dag.nodes["src"] = BuiltNode(step_id="src", fn=counting_source, source_ids={})

    prior = execute_built(dag, tmp_path)
    assert prior.outputs["src"].to_bytes("dev") == b"call-1"

    result = execute_partial_built(dag, ["src"], tmp_path, prior=prior)

    # Re-executed node produces a new value that wins over the prior snapshot
    assert result.outputs["src"].to_bytes("dev") == b"call-2"


def test_updated_param_flows_through_reexecution(tmp_path: Path) -> None:
    """Mutating param_values before execute_partial_built uses the new value."""
    received: dict[str, object] = {}

    def proc(image: _Img, *, level: int = 128) -> _Img:
        received["level"] = level
        return image

    dag = BuiltDAG()
    dag.nodes["src"] = _source_node("src")
    dag.nodes["proc"] = BuiltNode(
        step_id="proc",
        fn=proc,
        source_ids={"image": "src"},
        param_values={"level": 128},
    )

    prior = execute_built(dag, tmp_path)
    dag.nodes["proc"].param_values["level"] = 42
    execute_partial_built(dag, ["proc"], tmp_path, prior=prior)
    assert received["level"] == 42


# ---------------------------------------------------------------------------
# execute_partial_built — prior: ExecutionResult
# ---------------------------------------------------------------------------


def test_partial_upstream_reads_from_prior_not_node_output(tmp_path: Path) -> None:
    """Upstream values for non-reexecuted nodes come from prior.outputs, not node.output."""
    dag = _two_node_dag()
    prior = execute_built(dag, tmp_path)

    # Poison node.output to prove partial execution doesn't read it
    dag.nodes["source_img"].output = None

    result = execute_partial_built(dag, ["pass_img"], tmp_path, prior=prior)

    assert result.ok
    assert "pass_img" in result.executed
    assert isinstance(result.outputs["pass_img"], _Img)


def test_partial_missing_prior_output_triggers_upstream_failure(tmp_path: Path) -> None:
    """Missing prior.outputs entry for an upstream node triggers the failure path."""
    from sketchbook.core.executor import ExecutionResult

    dag = _two_node_dag()
    # Build a prior where source_img previously failed (absent from outputs)
    empty_prior = ExecutionResult()

    result = execute_partial_built(dag, ["pass_img"], tmp_path, prior=empty_prior)

    assert not result.ok
    assert "pass_img" in result.errors
    assert "pass_img" not in result.executed


def test_partial_outputs_is_full_snapshot(tmp_path: Path) -> None:
    """Returned outputs is a full snapshot: prior.outputs merged with newly-executed."""
    dag = BuiltDAG()
    dag.nodes["src_a"] = _source_node("src_a", b"a")
    dag.nodes["src_b"] = _source_node("src_b", b"b")
    dag.nodes["from_a"] = _passthrough_node("from_a", "src_a")
    dag.nodes["from_b"] = _passthrough_node("from_b", "src_b")

    prior = execute_built(dag, tmp_path)
    result = execute_partial_built(dag, ["src_b"], tmp_path, prior=prior)

    # Newly-executed nodes are present
    assert "src_b" in result.outputs
    assert "from_b" in result.outputs
    # Prior values for non-reexecuted nodes are also present
    assert "src_a" in result.outputs
    assert "from_a" in result.outputs
