from dataclasses import dataclass, field

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    SkipTheLineMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


class WorkerGoneError(Exception):
    """Raised at whatever was awaiting a worker's reply, once that worker will never send one.

    Carries the reason the worker went away, written where it is known -- eviction and a library
    reload are different stories and only their own call sites can tell them. Raised rather than
    cancelling the awaiting task, so a CancelledError keeps its single meaning: the flow was
    cancelled.

    Lives here, with the worker protocol's payloads, because both the manager that raises it and
    the manager that turns it into a node failure import it at runtime, and events are the leaf of
    the import graph.
    """


@dataclass
@PayloadRegistry.register
class RegisterWorkerRequest(RequestPayload):
    """Sent by a worker engine to the orchestrator's session topic to announce itself.

    The orchestrator stores the worker's engine_id and subscribes to the worker's
    dedicated response topic so it can relay results back to the GUI.

    Args:
        worker_engine_id: The engine_id of the registering worker.
        engine_version: The griptape_nodes engine version the worker is running.
            The orchestrator rejects registrations whose engine_version does not
            match its own; workers and orchestrators must share a version because
            the wire shape of every event is tied to the engine build.
        library_name: The library this worker exclusively serves, or None for a
            general-purpose worker that can handle any request.
    """

    worker_engine_id: str
    engine_version: str
    library_name: str | None = None
    broadcast_result: bool = field(default=False, kw_only=True)


@dataclass
@PayloadRegistry.register
class RegisterWorkerResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Worker registration succeeded.

    Carries no project: the orchestrator sends the worker's first activation down the same path a
    mid-session switch uses, so there is one sender and one adoption path rather than two that have
    to be ordered against each other.

    Args:
        worker_engine_id: The engine_id of the worker that was registered.
    """

    worker_engine_id: str


@dataclass
@PayloadRegistry.register
class RegisterWorkerResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Worker registration failed."""


@dataclass
@PayloadRegistry.register
class WorkerHeartbeatRequest(RequestPayload, SkipTheLineMixin):
    """Sent by the orchestrator to a worker to verify it is still alive.

    Uses SkipTheLineMixin so the worker processes it immediately without queuing,
    identical to SessionHeartbeatRequest and EngineHeartbeatRequest.

    Args:
        heartbeat_id: Correlation token to match request with response.
    """

    heartbeat_id: str


@dataclass
@PayloadRegistry.register
class WorkerHeartbeatResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Worker heartbeat succeeded — worker is alive.

    Args:
        heartbeat_id: Correlates with the originating WorkerHeartbeatRequest.
    """

    heartbeat_id: str


@dataclass
@PayloadRegistry.register
class DropWorkflowLocalObjectsRequest(RequestPayload, SkipTheLineMixin):
    """Sent by the orchestrator to each registered worker when a workflow's object state is cleared.

    Clearing a workflow deletes its nodes and so every key referring to an object held for it, leaving
    those objects unreachable while still holding what they hold. A broadcast rather than a local hook
    because the worker, not the orchestrator, is the process holding them.

    Acts on the workflow the request is addressed to, like any workflow request. The worker releases what
    it parked while running that workflow's nodes and keeps the objects of the other open workflows.

    SkipTheLineMixin for the same reason as its siblings: the alternative is a queued ExecuteNodeRequest
    running against objects belonging to a workflow that is already gone.
    """


@dataclass
@PayloadRegistry.register
class DropWorkflowLocalObjectsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Worker released every object it was holding for its libraries."""


@dataclass
@PayloadRegistry.register
class DropWorkflowLocalObjectsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Worker failed to release the objects it was holding."""


@dataclass
@PayloadRegistry.register
class SweepWorkflowRuntimesRequest(RequestPayload, SkipTheLineMixin):
    """Sent by the orchestrator to each worker on its heartbeat interval, naming the workflows it holds open.

    A worker keeps a namespace for each workflow it has run nodes for, and the orchestrator ends one with
    DropWorkflowLocalObjectsRequest when it clears that workflow. A drop that never arrives (lost in transit,
    or sent while the worker was reconnecting) would leave the namespace, and what the worker parked under
    it, for the life of the worker. This is the backstop: the worker releases the namespace of every
    workflow not named here.

    Uses SkipTheLineMixin so the worker compares the list against the workflows it holds at the moment it
    arrives. Queued behind a long node, it would be applied hours late against a list that no longer
    describes the orchestrator.

    Args:
        open_workflow_ids: The id of every workflow the orchestrator holds open.
    """

    open_workflow_ids: list[str]


@dataclass
@PayloadRegistry.register
class SweepWorkflowRuntimesResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Worker compared its workflows against the orchestrator's and released the ones that were gone."""


@dataclass
@PayloadRegistry.register
class SweepWorkflowRuntimesResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Worker could not release the workflows the orchestrator no longer holds."""


@dataclass
@PayloadRegistry.register
class UnregisterWorkerRequest(RequestPayload):
    """Sent by a worker to the orchestrator's session topic on graceful shutdown.

    Args:
        worker_engine_id: The engine_id of the departing worker.
    """

    worker_engine_id: str
    broadcast_result: bool = field(default=False, kw_only=True)


@dataclass
@PayloadRegistry.register
class UnregisterWorkerResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Worker unregistration succeeded.

    Args:
        worker_engine_id: The engine_id of the worker that was removed.
    """

    worker_engine_id: str


@dataclass
@PayloadRegistry.register
class UnregisterWorkerResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Worker unregistration failed."""


@dataclass
@PayloadRegistry.register
class StartWorkerRequest(RequestPayload):
    """Internal request to spawn a worker subprocess for a library that requires one.

    Sent by LibraryManager when a worker-delegated library finishes loading on the
    orchestrator. WorkerManager handles this by waiting for an active session then
    spawning the worker subprocess.

    Args:
        library_name: The library the worker will serve.
    """

    library_name: str
    broadcast_result: bool = field(default=False, kw_only=True)


@dataclass
@PayloadRegistry.register
class StartWorkerResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Worker spawn was successfully scheduled."""


@dataclass
@PayloadRegistry.register
class StartWorkerResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Worker spawn could not be scheduled."""
