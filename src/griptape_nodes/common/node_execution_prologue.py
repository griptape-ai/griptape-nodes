"""Shared pre-aprocess normalization for node execution.

Both the orchestrator-local execution path and the worker's
transient-node execution path need to massage ``BaseNode`` into the
same state before calling ``aprocess``: rehydrate serialized artifacts
in the request's parameter_values, push those values onto the node
(skipping no-op writes), materialize parameter defaults so direct
``self.parameter_values[name]`` reads see them, and reset the
cancellation flag from any prior run.

The two paths previously inlined near-identical versions of this pass
and drifted apart whenever one side was patched. Centralizing the
convergence here is how the strict-mode framework enforces
orchestrator/worker parity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.common.parameter_hydration import hydrate_parameter_values

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.retained_mode.events.execution_events import ExecuteNodeRequest


_PARAM_MISSING = object()


class ParameterHydrationError(Exception):
    """Raised when prepare_node_for_aprocess fails to set a parameter.

    Carries the parameter name so the caller can build a user-facing
    ExecuteNodeResultFailure with the standard wording.
    """

    def __init__(self, parameter_name: str, original: Exception) -> None:
        super().__init__(str(original))
        self.parameter_name = parameter_name
        self.original = original


async def prepare_node_for_aprocess(node: BaseNode, request: ExecuteNodeRequest) -> None:
    """Normalize ``node`` against ``request`` so aprocess can run.

    Performs, in order:
    1. Clear ``node._cancellation_requested`` (prior runs may have set it).
    2. Hydrate serialized artifacts in ``request.parameter_values`` and
       push each non-no-op value onto the node via ``set_parameter_value``.
    3. Materialize each parameter's ``default_value`` into
       ``node.parameter_values`` when the dict has no entry for the
       parameter (user ``process()`` code that reads the dict directly
       must see defaults on a fresh worker-side node).

    Raises:
        ParameterHydrationError: if ``set_parameter_value`` fails for
            any incoming parameter. The caller is expected to translate
            this into an ``ExecuteNodeResultFailure``.
    """
    node._cancellation_requested.clear()

    parameter_values = hydrate_parameter_values(request.parameter_values)
    for param_name, value in parameter_values.items():
        # Skip when the node already holds this value. The local path
        # calls ExecuteNodeRequest with dict(node.parameter_values) on
        # the same in-memory instance, so every iteration would be a
        # no-op mutation that still ran before/after_value_set hooks
        # and emitted a lifecycle event -- observably breaking nodes
        # like LoadImage. On the worker the node is fresh, so current
        # is _PARAM_MISSING and the normal set path runs.
        current = node.parameter_values.get(param_name, _PARAM_MISSING)
        if current is value or current == value:
            continue
        try:
            node.set_parameter_value(param_name, value)
        except Exception as e:
            raise ParameterHydrationError(param_name, e) from e

    # Materialize parameter defaults into parameter_values so that user
    # process() code reading self.parameter_values[name] directly (rather
    # than via get_parameter_value) sees the default. Newly-dropped nodes
    # never receive a SetParameterValueRequest for still-default values,
    # so without this pass those params are absent from the dict on the
    # worker-side fresh node.
    for param in node.parameters:
        if param.name in node.parameter_values:
            continue
        if param.default_value is None:
            continue
        node.parameter_values[param.name] = param.default_value
