"""Validate, before a flow starts, the nodes whose inputs are already known.

A node normally runs `validate_before_node_run` just before it's dispatched, after its upstream
nodes have run and handed it their outputs. Many inputs don't depend on this run, though: a value
set on the node itself, or an output from an upstream node this run won't execute (one that's
already `RESOLVED`, which the DAG builder skips, or locked). For a node whose every input is like
that, the check can run before the flow starts, so a bad input fails the run before anything else
runs, and problems on several nodes are reported together.

The inputs are handed to the check with `BaseNode.reading_inputs`, not set on the node, so looking
changes nothing: no node is marked unresolved and no `after_value_set` hook fires.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple

from griptape_nodes.exe_types.connections import Direction
from griptape_nodes.exe_types.core_types import ParameterTypeBuiltin
from griptape_nodes.exe_types.input_check_budget import input_check_budget
from griptape_nodes.exe_types.node_types import NodeResolutionState

if TYPE_CHECKING:
    from collections.abc import Iterable

    from griptape_nodes.exe_types.connections import Connections
    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["UpfrontValidationFailure", "known_inputs", "validate_nodes_with_known_inputs"]


class UpfrontValidationFailure(NamedTuple):
    """One node whose check failed before the flow started, with the exceptions it returned."""

    node: BaseNode
    exceptions: list[Exception]


def _wont_run(node: BaseNode) -> bool:
    """Whether this run will leave `node` as it is: it's already resolved, or it's locked."""
    return node.lock or node.state == NodeResolutionState.RESOLVED


def known_inputs(node: BaseNode, connections: Connections) -> dict[str, Any] | None:
    """The values `node`'s connected inputs will receive this run, or None if any isn't known yet.

    An input is known when the node feeding it won't run this time, so its output is already final.
    The values are read the way `collect_values_from_upstream_nodes` reads them. Inputs with no
    connection aren't included: the node already holds their values.
    """
    values: dict[str, Any] = {}
    for parameter in node.parameters:
        if parameter.output_type == ParameterTypeBuiltin.CONTROL_TYPE.value:
            continue
        upstream = connections.get_connected_node(node, parameter, direction=Direction.UPSTREAM)
        if upstream is None:
            continue
        upstream_node, upstream_parameter = upstream
        if not _wont_run(upstream_node):
            return None
        if upstream_parameter.name in upstream_node.parameter_output_values:
            values[parameter.name] = upstream_node.parameter_output_values[upstream_parameter.name]
        else:
            values[parameter.name] = upstream_node._get_raw_parameter_value(upstream_parameter.name)
    return values


def validate_nodes_with_known_inputs(
    nodes: Iterable[BaseNode], connections: Connections
) -> list[UpfrontValidationFailure]:
    """Run `validate_before_node_run` on every node in `nodes` whose inputs are all known.

    Nodes this run won't execute are skipped, as are nodes with an input that depends on a node that
    will run: those are checked just before they run, as usual. Each check runs under
    `input_check_budget()` with its inputs handed to it, not set. A check that raises is reported as
    a failure of that node rather than stopping the others.
    """
    failures: list[UpfrontValidationFailure] = []
    for node in nodes:
        if _wont_run(node):
            continue
        values = known_inputs(node, connections)
        if values is None:
            continue
        try:
            with node.reading_inputs(values), input_check_budget():
                exceptions = node.validate_before_node_run()
        except Exception as e:
            logger.exception("Checking node '%s' before the flow started raised", node.name)
            exceptions = [e]
        if exceptions:
            failures.append(UpfrontValidationFailure(node=node, exceptions=list(exceptions)))
    return failures
