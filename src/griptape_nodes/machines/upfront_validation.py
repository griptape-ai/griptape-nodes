"""Validate, before a flow starts, the nodes whose inputs are already known.

A node normally runs `validate_before_node_run` just before it's dispatched, after its upstream
nodes have run and handed it their outputs. Many inputs don't depend on this run, though: a value
set on the node itself, or an output from an upstream node this run won't execute (one that's
already `RESOLVED`, which the DAG builder skips, or locked). For a node whose every input is like
that, the check can run before the flow starts, so a bad input fails the run before anything else
runs, and problems on several nodes are reported together.

The inputs are set on the node first, exactly as the run sets them just before the node runs, so the
node's `after_value_set` hooks run and the check sees the same values it would at the node's turn.
Many nodes correct a dependent setting there, such as a duration the newly connected model doesn't
allow; setting the inputs is what lets the check judge the corrected value. The values written are
the ones the run would write a moment later.

An input that's a key for an object held in a worker process (a `serializable=False` value) isn't
treated as known. The check runs in the engine process, where that object can't be read, so it would
fail; at the node's turn that fails only the node, but up front it would stop the whole flow.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

from griptape_nodes.exe_types.connections import Direction
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.input_check_budget import input_check_budget
from griptape_nodes.exe_types.local_objects import collect_leaves, is_reference
from griptape_nodes.exe_types.node_types import NodeResolutionState
from griptape_nodes.machines.parallel_resolution import collect_upstream_values_into

if TYPE_CHECKING:
    from collections.abc import Iterable

    from griptape_nodes.exe_types.connections import Connections
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.retained_mode.engine import Engine

logger = logging.getLogger("griptape_nodes")

__all__ = ["UpfrontValidationFailure", "inputs_are_known", "validate_nodes_with_known_inputs"]


class UpfrontValidationFailure(NamedTuple):
    """One node whose check failed before the flow started, with the exceptions it returned."""

    node: BaseNode
    exceptions: list[Exception]


def _wont_run(node: BaseNode) -> bool:
    """Whether this run will leave `node` as it is: it's already resolved, or it's locked."""
    return node.lock or node.state == NodeResolutionState.RESOLVED


def inputs_are_known(node: BaseNode, connections: Connections) -> bool:
    """Whether every value `node`'s connected inputs will receive this run is already final.

    An input is known when the node feeding it won't run this time, so its output can't change. Inputs
    with no connection already hold their values. An input holding a key for an object kept in a worker
    process makes the node unknown, since its check can't read the object here.
    """
    for parameter in node.parameters:
        if parameter.output_type == ParameterTypeBuiltin.CONTROL_TYPE.value:
            continue
        upstream = connections.get_connected_node(node, parameter, direction=Direction.UPSTREAM)
        if upstream is None:
            continue
        upstream_node, upstream_parameter = upstream
        if not _wont_run(upstream_node):
            return False
        if upstream_parameter.name in upstream_node.parameter_output_values:
            value = upstream_node.parameter_output_values[upstream_parameter.name]
        else:
            value = upstream_node._get_raw_parameter_value(upstream_parameter.name)
        if collect_leaves(value, is_reference):
            return False
    return True


async def validate_nodes_with_known_inputs(
    engine: Engine, nodes: Iterable[BaseNode], connections: Connections
) -> list[UpfrontValidationFailure]:
    """Run `validate_before_node_run` on every node in `nodes` whose inputs are all known.

    Nodes this run won't execute are skipped, as are nodes with an input that depends on a node that
    will run: those are checked just before they run, as usual. Each node's connected inputs are set
    first, as the run sets them, and its check runs under `input_check_budget()`. A check that raises,
    or an input that can't be set, is reported as a failure of that node rather than stopping the others.
    """
    failures: list[UpfrontValidationFailure] = []
    for node in nodes:
        if _wont_run(node) or not inputs_are_known(node, connections):
            continue
        try:
            await collect_upstream_values_into(engine, node)
            with input_check_budget():
                exceptions = node.validate_before_node_run()
        except Exception as e:
            logger.exception("Checking node '%s' before the flow started raised", node.name)
            exceptions = [e]
        if exceptions:
            failures.append(UpfrontValidationFailure(node=node, exceptions=list(exceptions)))
    return failures
