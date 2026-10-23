from dataclasses import dataclass, field
from typing import Literal

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

    Also sent by the artist's engine to the machine its distribution settings assign the library
    to, with `worker_engine_id` set. That machine's engine then starts the worker under that id in
    the session of the engine that sent the request, so the worker registers with the artist's
    engine and serves it.

    Args:
        library_name: The library the worker will serve, or None for the general-purpose worker,
            which serves no single library and runs the nodes of Isolated Execution groups.
        worker_engine_id: The engine ID the worker takes, chosen by the artist's engine, or None for
            a worker of this engine's own session.
    """

    library_name: str | None
    worker_engine_id: str | None = None
    broadcast_result: bool = field(default=False, kw_only=True)


@dataclass
@PayloadRegistry.register
class StartWorkerResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Worker spawn was successfully scheduled."""


@dataclass
@PayloadRegistry.register
class StartWorkerResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Worker spawn could not be scheduled.

    Args:
        session_unknown: The request came from an artist's session on another machine that has not
            registered with this one, as after this machine restarts, or that registered without
            naming the library, as after its settings changed. It may register and ask again.
    """

    session_unknown: bool = False


@dataclass
@PayloadRegistry.register
class RegisterSessionRequest(RequestPayload):
    """Sent by the artist's engine to another machine's engine before asking it to start any worker.

    Sent once per session for each machine the distribution settings assign a library to. The
    machine registers the session of the engine that sent it, which its workers on that machine
    join. It refuses a session whose engine version differs from its own, because the wire shape of
    every event is tied to the engine build, and refuses each library whose version differs or
    that it does not have.

    Args:
        schema_version: The version of the distributed execution contract the artist's engine speaks.
        engine_version: The artist's engine version.
        library_versions: The version of each library the artist's engine will send to that machine.
        license_token: The artist's Griptape Nodes license, or None when it has none.
        static_server_base_url: Where the artist's engine serves the shared workspace, so the asset
            URLs its workers mint are ones the artist's editor can open.
        api_key: The artist's Griptape Cloud API key, or None when it has none. Workers started
            for the session run on the artist's license and API key, never the machine's own.
    """

    schema_version: str
    engine_version: str
    library_versions: dict[str, str]
    license_token: str | None = None
    static_server_base_url: str | None = None
    api_key: str | None = None
    broadcast_result: bool = field(default=False, kw_only=True)


@dataclass
@PayloadRegistry.register
class RegisterSessionResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """The machine accepted the artist's session.

    Args:
        engine_id: The machine's engine ID, so the artist's engine can tell it reached the machine
            its distribution settings name.
        refused_libraries: Each library it will not start workers for, with the reason.
    """

    engine_id: str = ""
    refused_libraries: dict[str, str] = field(default_factory=dict)


@dataclass
@PayloadRegistry.register
class RegisterSessionResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """The machine refused the artist's session, and will start no workers for it."""


@dataclass
@PayloadRegistry.register
class StopWorkerRequest(RequestPayload):
    """Sent by the artist's engine to the machine it asked to start a worker, to stop that worker.

    Sent when the start is withdrawn after it was sent, as when the library is reset while the
    machine has not answered yet. The machine reports the exit with `WorkerExitedRequest`.

    Args:
        worker_engine_id: The worker to stop, as named in the `StartWorkerRequest`. Only the engine
            that started it may stop it.
    """

    worker_engine_id: str
    broadcast_result: bool = field(default=False, kw_only=True)


@dataclass
@PayloadRegistry.register
class StopWorkerResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """The machine stopped the worker, or was not running it."""


@dataclass
@PayloadRegistry.register
class StopWorkerResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """The machine could not stop the worker."""


@dataclass
@PayloadRegistry.register
class WorkerExitedRequest(RequestPayload):
    """Sent by a machine to the artist's engine whenever a worker it runs for that artist exits.

    Sent for every exit, whatever ended the worker, so the artist's engine settles a start that
    never registered and removes a registered worker at once rather than after heartbeat eviction.

    Args:
        worker_engine_id: The worker that exited, as named in the `StartWorkerRequest`.
        exit_code: The worker process's exit code.
        reason: "stopped" when the machine stopped the worker on purpose, as when it shuts down or a
            new start replaces it, so the worker may be started again. "exited" when the worker
            ended on its own, as when it crashes or fails to start.
    """

    worker_engine_id: str
    exit_code: int
    reason: Literal["stopped", "exited"]
    broadcast_result: bool = field(default=False, kw_only=True)


@dataclass
@PayloadRegistry.register
class WorkerExitedResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """The artist's engine recorded the exit."""


@dataclass
@PayloadRegistry.register
class WorkerExitedResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """The exit was reported by a machine other than the one running the worker."""
