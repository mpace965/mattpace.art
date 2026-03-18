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


def test_topo_sort_three_node_chain_ordered() -> None:
    dag = DAG()
    for nid in ("src", "mid", "dst"):
        dag.add_node(_node(nid))
    dag.connect("src", "mid")
    dag.connect("mid", "dst")
    order = [n.id for n in dag.topo_sort()]
    assert order.index("src") < order.index("mid") < order.index("dst")


def test_edges_property_returns_all_edges() -> None:
    dag = DAG()
    for nid in ("a", "b", "c"):
        dag.add_node(_node(nid))
    dag.connect("a", "b", "image")
    dag.connect("b", "c", "image")
    edges = dag.edges
    assert ("a", "b", "image") in edges
    assert ("b", "c", "image") in edges


# ---------------------------------------------------------------------------
# node lookup
# ---------------------------------------------------------------------------

def test_node_lookup_missing_raises() -> None:
    dag = DAG()
    with pytest.raises(KeyError, match="No node 'x'"):
        dag.node("x")


# ---------------------------------------------------------------------------
# descendants
# ---------------------------------------------------------------------------

def test_descendants_leaf_node_is_empty() -> None:
    dag = DAG()
    dag.add_node(_node("a"))
    dag.add_node(_node("b"))
    dag.connect("a", "b")
    assert dag.descendants("b") == []


def test_descendants_simple_chain() -> None:
    dag = DAG()
    for nid in ("a", "b", "c"):
        dag.add_node(_node(nid))
    dag.connect("a", "b")
    dag.connect("b", "c")
    assert set(dag.descendants("a")) == {"b", "c"}


def test_descendants_direct_child_only() -> None:
    dag = DAG()
    for nid in ("a", "b", "c"):
        dag.add_node(_node(nid))
    dag.connect("a", "b")
    dag.connect("b", "c")
    assert set(dag.descendants("b")) == {"c"}


def test_descendants_branching() -> None:
    """Two children both appear as descendants."""
    dag = DAG()
    for nid in ("a", "b", "c"):
        dag.add_node(_node(nid))
    dag.connect("a", "b")
    dag.connect("a", "c")
    assert set(dag.descendants("a")) == {"b", "c"}


def test_descendants_diamond() -> None:
    """a → b → d, a → c → d: descendants of a = {b, c, d}."""
    dag = DAG()
    for nid in ("a", "b", "c", "d"):
        dag.add_node(_node(nid))
    dag.connect("a", "b")
    dag.connect("a", "c")
    dag.connect("b", "d")
    dag.connect("c", "d")
    assert set(dag.descendants("a")) == {"b", "c", "d"}


def test_descendants_missing_node_raises() -> None:
    dag = DAG()
    with pytest.raises(KeyError, match="No node 'z'"):
        dag.descendants("z")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

class _RequiredInputStep(_Stub):
    def setup(self) -> None:
        self.add_input("image", object)


class _OptionalInputStep(_Stub):
    def setup(self) -> None:
        self.add_input("image", object)
        self.add_input("mask", object, optional=True)


def test_validate_missing_required_raises() -> None:
    dag = DAG()
    dag.add_node(DAGNode(_RequiredInputStep(), "step"))
    with pytest.raises(ValueError, match="Required input 'image'.*step"):
        dag.validate()


def test_validate_connected_required_passes() -> None:
    dag = DAG()
    dag.add_node(_node("src"))
    dag.add_node(DAGNode(_RequiredInputStep(), "step"))
    dag.connect("src", "step", "image")
    dag.validate()  # should not raise


# ---------------------------------------------------------------------------
# node_depths
# ---------------------------------------------------------------------------

def test_node_depths_single_node() -> None:
    dag = DAG()
    dag.add_node(_node("a"))
    assert dag.node_depths() == {"a": 0}


def test_node_depths_chain() -> None:
    dag = DAG()
    for nid in ("a", "b", "c"):
        dag.add_node(_node(nid))
    dag.connect("a", "b")
    dag.connect("b", "c")
    depths = dag.node_depths()
    assert depths["a"] == 0
    assert depths["b"] == 1
    assert depths["c"] == 2


def test_node_depths_diamond() -> None:
    """Both short and long paths — depth is the longest."""
    dag = DAG()
    for nid in ("a", "b", "c", "d"):
        dag.add_node(_node(nid))
    dag.connect("a", "b")
    dag.connect("a", "c")
    dag.connect("b", "d")
    dag.connect("c", "d")
    depths = dag.node_depths()
    assert depths["a"] == 0
    assert depths["d"] == 2


def test_node_depths_two_roots() -> None:
    dag = DAG()
    for nid in ("a", "b", "c", "d"):
        dag.add_node(_node(nid))
    dag.connect("a", "c")
    dag.connect("b", "d")
    depths = dag.node_depths()
    assert depths["a"] == 0
    assert depths["b"] == 0
    assert depths["c"] == 1
    assert depths["d"] == 1


# ---------------------------------------------------------------------------
# connected_components
# ---------------------------------------------------------------------------

def test_connected_components_single_chain() -> None:
    dag = DAG()
    for nid in ("a", "b", "c"):
        dag.add_node(_node(nid))
    dag.connect("a", "b")
    dag.connect("b", "c")
    components = dag.connected_components()
    assert len(components) == 1
    assert set(components[0]) == {"a", "b", "c"}


def test_connected_components_two_isolated_chains() -> None:
    dag = DAG()
    for nid in ("a", "b", "x", "y"):
        dag.add_node(_node(nid))
    dag.connect("a", "b")
    dag.connect("x", "y")
    components = dag.connected_components()
    assert len(components) == 2
    as_sets = [set(c) for c in components]
    assert {"a", "b"} in as_sets
    assert {"x", "y"} in as_sets


def test_connected_components_each_group_in_topo_order() -> None:
    dag = DAG()
    for nid in ("a", "b", "c"):
        dag.add_node(_node(nid))
    dag.connect("a", "b")
    dag.connect("b", "c")
    components = dag.connected_components()
    group = components[0]
    assert group.index("a") < group.index("b") < group.index("c")


def test_connected_components_single_node() -> None:
    dag = DAG()
    dag.add_node(_node("solo"))
    components = dag.connected_components()
    assert components == [["solo"]]


def test_connected_components_diamond_is_one_component() -> None:
    dag = DAG()
    for nid in ("a", "b", "c", "d"):
        dag.add_node(_node(nid))
    dag.connect("a", "b")
    dag.connect("a", "c")
    dag.connect("b", "d")
    dag.connect("c", "d")
    components = dag.connected_components()
    assert len(components) == 1
    assert set(components[0]) == {"a", "b", "c", "d"}


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def test_validate_missing_optional_passes() -> None:
    """Required input connected, optional input not connected — should pass."""
    dag = DAG()
    dag.add_node(_node("src"))
    dag.add_node(DAGNode(_OptionalInputStep(), "step"))
    dag.connect("src", "step", "image")
    dag.validate()  # optional 'mask' not connected is fine
