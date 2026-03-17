"""Unit tests for DAG: add_node, connect, topo_sort, cycle detection, duplicate node error."""

from __future__ import annotations

import pytest

from sketchbook.core.dag import DAG, DAGNode
from sketchbook.core.step import PipelineStep


class _Stub(PipelineStep):
    def setup(self) -> None:
        pass

    def process(self, inputs, params):
        return None


def _node(node_id: str) -> DAGNode:
    return DAGNode(_Stub(), node_id)


# ---------------------------------------------------------------------------
# add_node
# ---------------------------------------------------------------------------

def test_add_node_stores_node() -> None:
    dag = DAG()
    n = _node("a")
    dag.add_node(n)
    assert dag.node("a") is n


def test_add_node_duplicate_raises() -> None:
    dag = DAG()
    dag.add_node(_node("a"))
    with pytest.raises(ValueError, match="already exists"):
        dag.add_node(_node("a"))


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------

def test_connect_adds_edge() -> None:
    dag = DAG()
    dag.add_node(_node("src"))
    dag.add_node(_node("dst"))
    dag.connect("src", "dst", "image")
    # The destination node should have its input wired
    assert dag.node("dst")._inputs["image"] is dag.node("src")


def test_connect_missing_source_raises() -> None:
    dag = DAG()
    dag.add_node(_node("dst"))
    with pytest.raises(ValueError, match="Source node 'src' not in DAG"):
        dag.connect("src", "dst")


def test_connect_missing_target_raises() -> None:
    dag = DAG()
    dag.add_node(_node("src"))
    with pytest.raises(ValueError, match="Target node 'dst' not in DAG"):
        dag.connect("src", "dst")


# ---------------------------------------------------------------------------
# topo_sort
# ---------------------------------------------------------------------------

def test_topo_sort_two_nodes() -> None:
    dag = DAG()
    dag.add_node(_node("a"))
    dag.add_node(_node("b"))
    dag.connect("a", "b")
    order = dag.topo_sort()
    assert [n.id for n in order] == ["a", "b"]


def test_topo_sort_chain() -> None:
    dag = DAG()
    for nid in ("a", "b", "c"):
        dag.add_node(_node(nid))
    dag.connect("a", "b")
    dag.connect("b", "c")
    order = dag.topo_sort()
    assert order.index(dag.node("a")) < order.index(dag.node("b"))
    assert order.index(dag.node("b")) < order.index(dag.node("c"))


def test_topo_sort_single_node() -> None:
    dag = DAG()
    dag.add_node(_node("solo"))
    assert [n.id for n in dag.topo_sort()] == ["solo"]


def test_topo_sort_cycle_raises() -> None:
    dag = DAG()
    dag.add_node(_node("a"))
    dag.add_node(_node("b"))
    dag.connect("a", "b")
    dag.connect("b", "a")
    with pytest.raises(ValueError, match="cycle"):
        dag.topo_sort()


# ---------------------------------------------------------------------------
# node lookup
# ---------------------------------------------------------------------------

def test_node_lookup_missing_raises() -> None:
    dag = DAG()
    with pytest.raises(KeyError, match="No node 'x'"):
        dag.node("x")
