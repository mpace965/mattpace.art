"""Unit tests for execute_built() and execute_partial_built()."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from sketchbook.core.built_dag import BuiltDAG, BuiltNode
from sketchbook.core.executor_v3 import execute_built, execute_partial_built
from sketchbook.core.protocol import SketchValueProtocol

# ---------------------------------------------------------------------------
# Minimal SketchValueProtocol implementation
# ---------------------------------------------------------------------------


class _Img:
    extension = "png"

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

    # Full execution first to populate outputs.
    execute_built(dag, tmp_path)

    # Modify source node's output to something distinguishable.
    dag.nodes["source_img"].output = _Img(b"changed")

    result = execute_partial_built(dag, ["source_img"], tmp_path)

    assert "source_img" in result.executed
    assert "pass_img" in result.executed


def test_partial_skips_unrelated_nodes(tmp_path: Path) -> None:
    """execute_partial_built skips nodes outside the affected subgraph."""
    dag = BuiltDAG()
    dag.nodes["src_a"] = _source_node("src_a", b"a")
    dag.nodes["src_b"] = _source_node("src_b", b"b")
    dag.nodes["from_a"] = _passthrough_node("from_a", "src_a")
    dag.nodes["from_b"] = _passthrough_node("from_b", "src_b")

    execute_built(dag, tmp_path)

    # Only re-execute from src_b.
    result = execute_partial_built(dag, ["src_b"], tmp_path)

    assert "src_b" in result.executed
    assert "from_b" in result.executed
    assert "src_a" not in result.executed
    assert "from_a" not in result.executed
