"""Unit tests for wire_sketch()."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pytest

from sketchbook.core.building_dag import output, source
from sketchbook.core.decorators import Param, SketchContext, sketch, step
from sketchbook.core.wiring import wire_sketch

# ---------------------------------------------------------------------------
# Minimal value type and loader for tests
# ---------------------------------------------------------------------------


class _Img:
    def __init__(self, data: bytes = b"") -> None:
        self.data = data


def _loader(path: Path) -> _Img:
    return _Img(path.read_bytes() if path.exists() else b"")


_CTX = SketchContext(mode="dev")


# ---------------------------------------------------------------------------
# Helper step functions
# ---------------------------------------------------------------------------


@step
def passthrough(image: _Img) -> _Img:
    """Return the image unchanged."""
    return image


@step
def blend(a: _Img, b: _Img) -> _Img:
    """Blend two images."""
    return _Img(a.data + b.data)


@step
def with_optional(image: _Img, mask: _Img | None = None) -> _Img:
    """Step with an optional mask input."""
    return image


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_single_step_sketch_node_order(tmp_path: Path) -> None:
    """source → passthrough → output produces 2 nodes in topo order."""
    src = tmp_path / "hello.png"
    src.write_bytes(b"fake")

    @sketch(date="2026-01-01")
    def hello() -> None:
        img = source(src, _loader)
        result = passthrough(img)
        output(result, "main")

    dag = wire_sketch(hello, _CTX)
    nodes = dag.topo_sort()
    assert len(nodes) == 2
    assert nodes[0].step_id == "source_hello"
    assert nodes[1].step_id == "passthrough"


def test_passthrough_source_ids(tmp_path: Path) -> None:
    """passthrough.source_ids == {'image': 'source_hello'}."""
    src = tmp_path / "hello.png"
    src.write_bytes(b"fake")

    @sketch(date="2026-01-01")
    def hello() -> None:
        img = source(src, _loader)
        result = passthrough(img)
        output(result, "main")

    dag = wire_sketch(hello, _CTX)
    assert dag.nodes["passthrough"].source_ids == {"image": "source_hello"}


def test_two_step_chain(tmp_path: Path) -> None:
    """source → passthrough → blend produces correct source_ids chain."""
    src_a = tmp_path / "a.png"
    src_b = tmp_path / "b.png"
    src_a.write_bytes(b"a")
    src_b.write_bytes(b"b")

    @sketch(date="2026-01-01")
    def two_step() -> None:
        a = source(src_a, _loader)
        b = source(src_b, _loader)
        pa = passthrough(a)
        result = blend(pa, b)
        output(result, "main")

    dag = wire_sketch(two_step, _CTX)
    assert dag.nodes["passthrough"].source_ids == {"image": "source_a"}
    assert dag.nodes["blend"].source_ids == {"a": "passthrough", "b": "source_b"}


def test_output_nodes_recorded(tmp_path: Path) -> None:
    """output_nodes contains the correct (step_id, bundle_name, presets) tuple."""
    src = tmp_path / "hello.png"
    src.write_bytes(b"fake")

    @sketch(date="2026-01-01")
    def hello() -> None:
        img = source(src, _loader)
        result = passthrough(img)
        output(result, "main", presets=["soft"])

    dag = wire_sketch(hello, _CTX)
    assert len(dag.output_nodes) == 1
    step_id, bundle, presets = dag.output_nodes[0]
    assert step_id == "passthrough"
    assert bundle == "main"
    assert presets == ["soft"]


def test_unknown_proxy_raises(tmp_path: Path) -> None:
    """A step referencing an unrecognised proxy raises ValueError."""
    from sketchbook.core.building_dag import Proxy

    @sketch(date="2026-01-01")
    def bad() -> None:
        # Manually inject a proxy that was never recorded
        fake_proxy = Proxy(step_id="nonexistent")
        passthrough(fake_proxy)

    with pytest.raises(ValueError, match="unknown proxy"):
        wire_sketch(bad, _CTX)


def test_missing_required_input_raises(tmp_path: Path) -> None:
    """Passing a non-Proxy to a required input raises ValueError at wire time."""
    src = tmp_path / "hello.png"
    src.write_bytes(b"fake")

    @sketch(date="2026-01-01")
    def bad() -> None:
        source(src, _loader)  # creates a proxy but never passes it to passthrough
        passthrough(_Img())  # _Img is not a Proxy — required input unconnected

    with pytest.raises(ValueError, match="required input"):
        wire_sketch(bad, _CTX)


def test_sketch_dir_resolves_relative_paths(tmp_path: Path) -> None:
    """wire_sketch(sketch_dir=...) resolves relative source paths to absolute."""
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "photo.png").write_bytes(b"fake")

    @sketch(date="2026-01-01")
    def relative_sketch() -> None:
        img = source("assets/photo.png", _loader)
        output(img, "main")

    dag = wire_sketch(relative_sketch, _CTX, sketch_dir=tmp_path)
    path, sid = dag.source_paths[0]
    assert path.is_absolute()
    assert path == tmp_path / "assets" / "photo.png"


def test_descendants_empty_for_leaf() -> None:
    """descendants() returns [] for a node with no downstream dependents."""
    src = Path("/fake/hello.png")

    @sketch(date="2026-01-01")
    def hello() -> None:
        img = source(src, _loader)
        result = passthrough(img)
        output(result, "main")

    dag = wire_sketch(hello, _CTX)
    # passthrough has no downstream nodes
    assert dag.descendants("passthrough") == []


def test_descendants_of_source(tmp_path: Path) -> None:
    """descendants(source_id) returns all nodes that transitively depend on it."""
    src = tmp_path / "hello.png"
    src.write_bytes(b"fake")

    @sketch(date="2026-01-01")
    def hello() -> None:
        img = source(src, _loader)
        result = passthrough(img)
        output(result, "main")

    dag = wire_sketch(hello, _CTX)
    desc = dag.descendants("source_hello")
    assert "passthrough" in desc


# ---------------------------------------------------------------------------
# param_schema / param_values population
# ---------------------------------------------------------------------------

_src = Path("/fake/hello.png")


def test_step_with_param_populates_schema() -> None:
    """wire_sketch fills param_schema from Annotated keyword args."""

    @step
    def proc(image: _Img, *, level: Annotated[int, Param(min=0, max=255)] = 128) -> _Img:
        return image

    @sketch(date="2026-01-01")
    def sk() -> None:
        img = source(_src, _loader)
        output(proc(img), "main")

    dag = wire_sketch(sk, _CTX)
    node = dag.nodes["proc"]
    assert len(node.param_schema) == 1
    assert node.param_schema[0].name == "level"
    assert node.param_values == {"level": 128}


def test_param_values_use_defaults() -> None:
    """Initial param_values come from function signature defaults."""

    @step
    def proc(image: _Img, *, sigma: Annotated[float, Param()] = 2.5) -> _Img:
        return image

    @sketch(date="2026-01-01")
    def sk() -> None:
        img = source(_src, _loader)
        output(proc(img), "main")

    dag = wire_sketch(sk, _CTX)
    assert dag.nodes["proc"].param_values["sigma"] == 2.5


def test_step_without_params_has_empty_schema() -> None:
    """A step with no Annotated params gets empty param_schema and param_values."""

    @sketch(date="2026-01-01")
    def sk() -> None:
        img = source(_src, _loader)
        output(passthrough(img), "main")

    dag = wire_sketch(sk, _CTX)
    node = dag.nodes["passthrough"]
    assert node.param_schema == []
    assert node.param_values == {}


def test_step_with_ctx_stores_context() -> None:
    """wire_sketch stores the dag-level ctx on a node whose step declares SketchContext."""

    @step
    def proc(image: _Img, ctx: SketchContext) -> _Img:
        return image

    @sketch(date="2026-01-01")
    def sk() -> None:
        img = source(_src, _loader)
        output(proc(img), "main")

    dag = wire_sketch(sk, _CTX)
    assert dag.nodes["proc"].ctx is _CTX
