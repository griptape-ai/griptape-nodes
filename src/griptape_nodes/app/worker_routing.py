"""Worker-side dispatch overrides for orchestrator-owned request types.

On a worker, a handful of request types must be serviced by the orchestrator
because the authoritative state (flow graph, connections, node registry) lives
there. This module provides:

- ``FORWARDED_REQUEST_TYPES``: the flat list of request classes whose worker-
  side handler should forward to the orchestrator.
- ``RemoteHandler``: an async callable that replaces the original manager
  handler for those request types on the worker. While the worker is actively
  executing a node it forwards; outside that scope it delegates back to the
  original local handler (which preserves bootstrap / library-load behavior).
- ``install_remote_handlers``: swaps the dispatch table entries on a
  just-configured worker after ``configure_worker_forwarding`` has wired up
  the RequestClient and loop references.

The routing decision lives entirely on the worker. Events themselves carry no
routing metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from griptape_nodes.retained_mode.events.config_events import (
    ResetConfigRequest,
    SetConfigCategoryRequest,
    SetConfigValueRequest,
)
from griptape_nodes.retained_mode.events.connection_events import (
    CreateConnectionRequest,
    DeleteConnectionRequest,
    ListConnectionsForNodeRequest,
)
from griptape_nodes.retained_mode.events.flow_events import (
    CreateFlowRequest,
    DeleteFlowRequest,
    ListFlowsInCurrentContextRequest,
    ListFlowsInFlowRequest,
    ListNodesInFlowRequest,
)
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    DeleteNodeRequest,
    GetFlowForNodeRequest,
    ListParametersOnNodeRequest,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    AddParameterToNodeRequest,
    AlterParameterDetailsRequest,
    GetConnectionsForParameterRequest,
    GetParameterDetailsRequest,
    GetParameterValueRequest,
    RemoveParameterFromNodeRequest,
    SetParameterValueRequest,
)
from griptape_nodes.retained_mode.events.secrets_events import (
    DeleteSecretValueRequest,
    SetSecretValueRequest,
)
from griptape_nodes.retained_mode.managers.event_manager import ResultContext
from griptape_nodes.utils.async_utils import call_function

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import (
        RequestPayload,
        ResultPayload,
    )
    from griptape_nodes.retained_mode.managers.event_manager import EventManager


HandlerCallback = "Callable[[RequestPayload], ResultPayload | Awaitable[ResultPayload]]"


FORWARDED_REQUEST_TYPES: frozenset[type[RequestPayload]] = frozenset(
    {
        # connection_events
        CreateConnectionRequest,
        DeleteConnectionRequest,
        ListConnectionsForNodeRequest,
        # node_events
        CreateNodeRequest,
        DeleteNodeRequest,
        ListParametersOnNodeRequest,
        GetFlowForNodeRequest,
        # parameter_events
        AddParameterToNodeRequest,
        RemoveParameterFromNodeRequest,
        SetParameterValueRequest,
        GetParameterDetailsRequest,
        AlterParameterDetailsRequest,
        GetParameterValueRequest,
        GetConnectionsForParameterRequest,
        # flow_events
        CreateFlowRequest,
        DeleteFlowRequest,
        ListNodesInFlowRequest,
        ListFlowsInCurrentContextRequest,
        ListFlowsInFlowRequest,
        # config_events
        SetConfigValueRequest,
        SetConfigCategoryRequest,
        ResetConfigRequest,
        # secrets_events
        SetSecretValueRequest,
        DeleteSecretValueRequest,
    }
)


@dataclass
class RemoteHandler:
    """Worker-side dispatch shim.

    Registered in place of the original manager handler for types in
    FORWARDED_REQUEST_TYPES. Forwards to the orchestrator while the worker is
    inside a ``worker_node_execution_scope``; delegates to the original
    handler otherwise (so bootstrap / library-load paths keep running locally).

    ``original`` is the handler this shim replaced and MUST be retained so the
    out-of-scope fallback can still service requests that bootstrap code makes
    (e.g. ``self.add_parameter(...)`` issuing ``AddParameterToNodeRequest``
    from a node's ``__init__`` under a LOAD_PROBE scope).
    """

    original: Any  # HandlerCallback; typed loosely to avoid a runtime import cycle
    event_manager: EventManager

    async def __call__(self, request: RequestPayload) -> ResultPayload:
        if self.event_manager.in_node_execution():
            event_result = await self.event_manager.forward_to_orchestrator(request, ResultContext())
            return cast("ResultPayload", event_result.result)
        return await call_function(self.original, request)


def install_remote_handlers(event_manager: EventManager) -> None:
    """Swap every FORWARDED_REQUEST_TYPE handler for a RemoteHandler.

    Must be called after every manager that claims one of these request types
    has finished registering (i.e. after ``GriptapeNodes()`` construction is
    complete) AND after ``configure_worker_forwarding`` has supplied the
    RequestClient / topic / loop references. See ``_run_worker`` in app.py.

    Raises RuntimeError if a forwarded request type has no registered owner;
    that always indicates a bootstrap-order bug, not a runtime condition.
    """
    for request_type in FORWARDED_REQUEST_TYPES:
        original = event_manager.get_manager_for_request_type(request_type)
        if original is None:
            msg = (
                f"install_remote_handlers: no manager registered for "
                f"{request_type.__name__}. Worker bootstrap must finish manager "
                f"registration before remote handlers are installed."
            )
            raise RuntimeError(msg)
        remote = RemoteHandler(original=original, event_manager=event_manager)
        event_manager.remove_manager_from_request_type(request_type)
        event_manager.assign_manager_to_request_type(request_type, remote)
