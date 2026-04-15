"""wire_sketch — resolves a @sketch function into a BuiltDAG."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from sketchbook.core.building_dag import Proxy, SourceRecord, building_sketch
from sketchbook.core.built_dag import BuiltDAG, BuiltNode
from sketchbook.core.decorators import SketchContext
from sketchbook.core.introspect import extract_inputs, extract_params

log = logging.getLogger("sketchbook.wiring")


def wire_sketch(
    fn: Callable,
    ctx: SketchContext,
    sketch_dir: Path | None = None,
) -> BuiltDAG:
    """Run *fn* inside building_sketch() and resolve recorded calls into a BuiltDAG.

    Args:
        fn: A @sketch-decorated function.
        ctx: The SketchContext to associate with each node.
        sketch_dir: If provided, relative source paths are resolved against this
            directory before being stored in source_paths and the loader lambda.

    Raises:
        ValueError: If a Proxy arg references an unknown step, or a required
            input has no corresponding Proxy argument.
    """
    with building_sketch() as bdag:
        fn()

    dag = BuiltDAG()
    known_ids: set[str] = set()

    # -----------------------------------------------------------------------
    # Process sources — these have no dependencies, so they come first.
    # -----------------------------------------------------------------------
    for record in bdag.sources:
        path = record.path
        if sketch_dir is not None and not path.is_absolute():
            path = sketch_dir / path

        node = BuiltNode(
            step_id=record.step_id,
            fn=_make_source_fn(record, path),
            source_ids={},
            ctx=ctx,
        )
        dag.nodes[record.step_id] = node
        dag.source_paths.append((path, record.step_id))
        known_ids.add(record.step_id)
        log.debug(f"Wired source node '{record.step_id}' → {path}")

    # -----------------------------------------------------------------------
    # Process step calls — recorded in topo order by Python evaluation.
    # -----------------------------------------------------------------------
    for call in bdag.steps:
        input_specs = extract_inputs(call.fn)
        source_ids: dict[str, str] = {}

        for i, arg in enumerate(call.args):
            if not isinstance(arg, Proxy):
                continue
            if arg.step_id not in known_ids:
                raise ValueError(
                    f"Step '{call.step_id}': argument {i} references unknown proxy "
                    f"'{arg.step_id}'. Known IDs: {sorted(known_ids)}"
                )
            if i >= len(input_specs):
                raise ValueError(
                    f"Step '{call.step_id}': more proxy arguments ({i + 1}) than "
                    f"declared inputs ({len(input_specs)})"
                )
            source_ids[input_specs[i].name] = arg.step_id

        # Validate all required inputs are connected.
        for spec in input_specs:
            if not spec.optional and spec.name not in source_ids:
                raise ValueError(
                    f"Step '{call.step_id}': required input '{spec.name}' has no "
                    f"corresponding proxy argument"
                )

        param_specs = extract_params(call.fn)
        param_values = {s.name: s.default for s in param_specs}

        node = BuiltNode(
            step_id=call.step_id,
            fn=call.fn,
            source_ids=source_ids,
            param_schema=param_specs,
            param_values=param_values,
            ctx=ctx,
        )
        dag.nodes[call.step_id] = node
        known_ids.add(call.step_id)
        log.debug(f"Wired step node '{call.step_id}' with inputs {source_ids}")

    # -----------------------------------------------------------------------
    # Process output declarations.
    # -----------------------------------------------------------------------
    for record in bdag.outputs:
        dag.output_nodes.append((record.source_proxy.step_id, record.bundle_name, record.presets))

    return dag


def _make_source_fn(record: SourceRecord, resolved_path: Path) -> Callable:
    """Return a zero-argument callable that loads the source file."""
    loader = record.loader
    return lambda: loader(resolved_path)
