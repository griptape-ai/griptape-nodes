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
- ``register_remote_handlers``: swaps the dispatch table entries on a
  just-configured worker after ``configure_worker_forwarding`` has wired up
  the RequestClient and loop references.
- ``ReloadConfigRequest`` / ``RefreshSecretsRequest`` and their Success/Failure
  payloads: orchestrator-originated broadcasts that every worker handles
  locally to re-read shared on-disk state. They live here, not in
  ``worker_events.py``, because their reason for existing is a routing
  decision (orchestrator fan-out to all workers); the names are deliberately
  free of any "Worker" prefix because, by this module's principle, an event's
  type carries no routing metadata.

The routing decision lives entirely on the worker. Events themselves carry no
routing metadata.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    SkipTheLineMixin,
    WorkflowNotAlteredMixin,
)
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
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.events.secrets_events import (
    DeleteSecretValueRequest,
    SetSecretValueRequest,
)
from griptape_nodes.retained_mode.managers.event_manager import ResultContext
from griptape_nodes.utils.async_utils import call_function

logger = logging.getLogger("griptape_nodes")

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager


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
@PayloadRegistry.register
class ReloadConfigRequest(RequestPayload, SkipTheLineMixin):
    """Sent by the orchestrator to each registered worker after a config mutation succeeds.

    On the same machine orchestrator and workers share
    ~/.config/griptape_nodes/griptape_nodes_config.json, but a worker's
    in-memory merged_config only reflects what it read on boot. This tells
    the worker to re-read the file so subsequent get_config_value calls
    see the new value.

    Uses SkipTheLineMixin so the worker processes it immediately, ahead of
    any queued ExecuteNodeRequest that would otherwise observe stale config.
    """


@dataclass
@PayloadRegistry.register
class ReloadConfigResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Worker reloaded its config from disk."""


@dataclass
@PayloadRegistry.register
class ReloadConfigResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Worker failed to reload its config from disk."""


@dataclass
@PayloadRegistry.register
class RefreshSecretsRequest(RequestPayload, SkipTheLineMixin):
    """Sent by the orchestrator to each registered worker after a secret mutation succeeds.

    The global .env at ~/.config/griptape_nodes/.env is shared across
    processes on the same machine, but the worker's os.environ snapshot
    was populated at boot from the file as it existed then. Without this
    refresh, get_secret() would see the stale env-var shadow (its highest
    priority source) even after the orchestrator updated the file.

    Uses SkipTheLineMixin to avoid a queued ExecuteNodeRequest reading
    the stale secret before the refresh lands.
    """


@dataclass
@PayloadRegistry.register
class RefreshSecretsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Worker refreshed its secrets from the shared .env file."""


@dataclass
@PayloadRegistry.register
class RefreshSecretsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Worker failed to refresh its secrets."""


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


def schedule_broadcast(broadcast_type: type[RequestPayload]) -> None:
    """Ask the orchestrator's WorkerManager to fan ``broadcast_type`` out to every worker.

    Use this from a manager's request handler (orchestrator-side) to fire the
    matching broadcast after a successful local mutation -- e.g. ``ConfigManager``
    calls ``schedule_broadcast(ReloadConfigRequest)`` after persisting a config
    write. No-op when the GriptapeNodes singleton has not been instantiated yet
    (isolated unit tests that construct managers on their own) or when no
    workers are registered.

    Imports the singleton lazily because this module is loaded during engine
    boot, before the GriptapeNodes accessor is ready.
    """
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    from griptape_nodes.utils.metaclasses import SingletonMeta

    if GriptapeNodes not in SingletonMeta._instances:
        return
    GriptapeNodes.WorkerManager().schedule_broadcast(broadcast_type)


def register_remote_handlers(event_manager: EventManager) -> None:
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
                f"register_remote_handlers: no manager registered for "
                f"{request_type.__name__}. Worker bootstrap must finish manager "
                f"registration before remote handlers are installed."
            )
            raise RuntimeError(msg)
        remote = RemoteHandler(original=original, event_manager=event_manager)
        event_manager.remove_manager_from_request_type(request_type)
        event_manager.assign_manager_to_request_type(request_type, remote)


def register_broadcast_handlers(
    event_manager: EventManager,
    *,
    config_manager: ConfigManager,
    secrets_manager: SecretsManager,
) -> None:
    """Install worker-side handlers for orchestrator-originated broadcasts.

    Workers receive ``ReloadConfigRequest`` / ``RefreshSecretsRequest`` from
    the orchestrator and respond by re-reading the shared on-disk state. The
    actual reload is delegated to the corresponding manager so domain logic
    stays in the manager and routing decisions stay here.
    """

    def handle_reload_config(request: ReloadConfigRequest) -> ResultPayload:  # noqa: ARG001
        try:
            config_manager.load_configs()
        except Exception as e:
            details = f"Attempted to reload config from disk. Failed because of {type(e).__name__}: {e}."
            logger.error(details)
            return ReloadConfigResultFailure(result_details=details)
        return ReloadConfigResultSuccess(result_details="Reloaded config from disk.")

    def handle_refresh_secrets(request: RefreshSecretsRequest) -> ResultPayload:  # noqa: ARG001
        try:
            secrets_manager.refresh_from_env_file()
        except Exception as e:
            details = f"Attempted to refresh secrets from shared .env file. Failed because of {type(e).__name__}: {e}."
            logger.error(details)
            return RefreshSecretsResultFailure(result_details=details)
        return RefreshSecretsResultSuccess(result_details="Refreshed secrets from shared .env file.")

    event_manager.assign_manager_to_request_type(ReloadConfigRequest, handle_reload_config)
    event_manager.assign_manager_to_request_type(RefreshSecretsRequest, handle_refresh_secrets)
