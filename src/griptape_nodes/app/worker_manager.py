from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
import uuid
from typing import TYPE_CHECKING

from griptape_nodes.bootstrap.utils.subprocess_websocket_base import WebSocketMessage
from griptape_nodes.retained_mode.events import worker_events
from griptape_nodes.retained_mode.events.base_events import EventRequest

if TYPE_CHECKING:
    import concurrent.futures
    from collections.abc import Awaitable, Callable

    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.library_manager import LibraryManager

logger = logging.getLogger("griptape_nodes_app")


class WorkerManager:
    """Manages worker registration, heartbeating, eviction, and event routing.

    Encapsulates all state and logic related to worker engines on both the
    orchestrator side (registry, heartbeat challenges, eviction, result relay)
    and the worker side (heartbeat response, self-termination monitor).

    Transport operations (subscribe, unsubscribe, send message) are injected
    as callables so this class has no direct dependency on WebSocket plumbing.
    """

    HEARTBEAT_INTERVAL_S: float = 5.0
    HEARTBEAT_TIMEOUT_S: float = 15.0
    NODE_EXECUTION_TIMEOUT_S: float = 300.0

    _WORKER_RESPONSE_TOPIC_RE: re.Pattern = re.compile(r"sessions/[^/]+/workers/(?P<worker_engine_id>[^/]+)/response$")

    def __init__(  # noqa: PLR0913
        self,
        *,
        griptape_nodes: GriptapeNodes,
        event_manager: EventManager,
        ws_outgoing_queue: asyncio.Queue,
        send_message: Callable[[str, str, str | None], Awaitable[None]],
        subscribe_to_topic: Callable[[str], Awaitable[None]],
        unsubscribe_from_topic: Callable[[str], Awaitable[None]],
    ) -> None:
        self._griptape_nodes = griptape_nodes
        self._ws_outgoing_queue = ws_outgoing_queue
        self._send_message = send_message
        self._subscribe_to_topic = subscribe_to_topic
        self._unsubscribe_from_topic = unsubscribe_from_topic

        # Orchestrator-side registry: worker_engine_id → worker request topic
        self._registered_workers: dict[str, str] = {}

        # Orchestrator-side: library_name → list of (engine_id, request_topic) tuples.
        # Today: at most one entry per library. Future: N workers per library.
        self._library_workers: dict[str, list[tuple[str, str]]] = {}

        # Orchestrator-side reverse lookup: worker_engine_id → library_name (or None for general workers)
        self._worker_library: dict[str, str | None] = {}

        # Subprocesses spawned by this orchestrator (library_name → process)
        self._managed_worker_processes: dict[str, asyncio.subprocess.Process] = {}

        # Orchestrator-side: worker_engine_id → monotonic timestamp of last heartbeat response
        self._worker_last_seen: dict[str, float] = {}

        # Worker-side: monotonic timestamp of last heartbeat received from the orchestrator
        self._worker_heartbeat_last_received_at: float = 0.0

        # Pending worker requests: request_id → Future resolved by relay_worker_result
        self._pending_requests: dict[str, asyncio.Future[dict]] = {}

        # Callbacks invoked when a worker is evicted: (worker_engine_id, library_name | None)
        self._worker_evicted_callbacks: list[Callable[[str, str | None], None]] = []

        event_manager.assign_manager_to_request_type(
            worker_events.RegisterWorkerRequest, self.handle_register_worker_request
        )
        event_manager.assign_manager_to_request_type(
            worker_events.WorkerHeartbeatRequest, self.handle_worker_heartbeat_request
        )
        event_manager.assign_manager_to_request_type(
            worker_events.UnregisterWorkerRequest, self.handle_unregister_worker_request
        )

    async def handle_register_worker_request(
        self,
        request: worker_events.RegisterWorkerRequest,
    ) -> worker_events.RegisterWorkerResultSuccess | worker_events.RegisterWorkerResultFailure:
        """Handle a worker registration request from a worker engine."""
        wid = request.worker_engine_id
        session_id = self._griptape_nodes.get_session_id()
        request_topic = f"sessions/{session_id}/workers/{wid}/request"
        self._registered_workers[wid] = request_topic
        self._worker_last_seen[wid] = time.monotonic()

        # Track library association for library-aware routing.
        self._worker_library[wid] = request.library_name
        if request.library_name:
            self._library_workers.setdefault(request.library_name, []).append((wid, request_topic))
            logger.info("Worker registered: %s → library '%s'", wid, request.library_name)
        else:
            logger.info("Worker registered: %s (general-purpose)", wid)

        response_topic = f"sessions/{session_id}/workers/{wid}/response"
        await self._subscribe_to_topic(response_topic)
        return worker_events.RegisterWorkerResultSuccess(
            worker_engine_id=wid, result_details="Worker registered successfully."
        )

    def handle_worker_heartbeat_request(
        self,
        request: worker_events.WorkerHeartbeatRequest,
    ) -> worker_events.WorkerHeartbeatResultSuccess:
        """Respond to an orchestrator heartbeat challenge."""
        self._worker_heartbeat_last_received_at = time.monotonic()
        return worker_events.WorkerHeartbeatResultSuccess(
            heartbeat_id=request.heartbeat_id,
            result_details="Worker alive.",
        )

    async def handle_unregister_worker_request(
        self,
        request: worker_events.UnregisterWorkerRequest,
    ) -> worker_events.UnregisterWorkerResultSuccess | worker_events.UnregisterWorkerResultFailure:
        """Handle a worker unregister request from a worker engine."""
        wid = request.worker_engine_id
        session_id = self._griptape_nodes.get_session_id()
        self._registered_workers.pop(wid, None)
        self._worker_last_seen.pop(wid, None)
        lib_name = self._worker_library.get(wid)
        self._deregister_worker_library(wid)
        response_topic = f"sessions/{session_id}/workers/{wid}/response"
        await self._unsubscribe_from_topic(response_topic)
        # Remove the managed process entry so a new worker can be spawned for this library.
        if lib_name:
            self._managed_worker_processes.pop(lib_name, None)
        logger.info("Worker unregistered: %s", wid)
        return worker_events.UnregisterWorkerResultSuccess(worker_engine_id=wid, result_details="Worker unregistered.")

    async def orchestrator_heartbeat_loop(self) -> None:
        """Challenge each registered worker on an interval; evict those that go silent."""
        while True:
            await asyncio.sleep(WorkerManager.HEARTBEAT_INTERVAL_S)
            if not self._registered_workers:
                continue

            now = time.monotonic()
            stale = [
                wid
                for wid in list(self._registered_workers)
                if now - self._worker_last_seen.get(wid, 0) > WorkerManager.HEARTBEAT_TIMEOUT_S
            ]
            for wid in stale:
                await self.evict_worker(wid)

            session_id = self._griptape_nodes.get_session_id()
            for wid, request_topic in list(self._registered_workers.items()):
                hb = EventRequest(
                    request=worker_events.WorkerHeartbeatRequest(heartbeat_id=str(uuid.uuid4())),
                    response_topic=f"sessions/{session_id}/workers/{wid}/response",
                )
                await self._ws_outgoing_queue.put(WebSocketMessage("EventRequest", hb.json(), request_topic))

    async def worker_heartbeat_monitor(self) -> None:
        """Shut down the worker if orchestrator heartbeats stop arriving."""
        self._worker_heartbeat_last_received_at = time.monotonic()  # seed to avoid immediate timeout
        while True:
            await asyncio.sleep(WorkerManager.HEARTBEAT_INTERVAL_S)
            elapsed = time.monotonic() - self._worker_heartbeat_last_received_at
            if elapsed > WorkerManager.HEARTBEAT_TIMEOUT_S:
                msg = f"Orchestrator heartbeat lost ({elapsed:.1f}s since last heartbeat); worker is shutting down."
                logger.warning(msg)
                raise RuntimeError(msg)

    def get_active_worker(self) -> tuple[str, str] | None:
        """Return (worker_engine_id, worker_request_topic) for the registered worker, or None."""
        return next(iter(self._registered_workers.items()), None)

    def get_worker_for_library(self, library_name: str) -> tuple[str, str] | None:
        """Return (worker_engine_id, worker_request_topic) for a worker serving library_name, or None.

        Today returns the first registered worker for the library. Future versions can
        load-balance across multiple workers for the same library.
        """
        workers = self._library_workers.get(library_name, [])
        return workers[0] if workers else None

    def _deregister_worker_library(self, worker_engine_id: str) -> None:
        """Remove a worker from the library routing tables."""
        lib = self._worker_library.pop(worker_engine_id, None)
        if lib and lib in self._library_workers:
            self._library_workers[lib] = [
                (eid, topic) for eid, topic in self._library_workers[lib] if eid != worker_engine_id
            ]
            if not self._library_workers[lib]:
                del self._library_workers[lib]

    @property
    def _websocket_event_loop(self) -> asyncio.AbstractEventLoop | None:
        """Return the WebSocket event loop from app.py, or None if not available.

        Uses a lazy import to avoid a circular dependency between worker_manager and app.
        """
        try:
            from griptape_nodes.app import app as _app
        except (ImportError, AttributeError):
            return None
        else:
            return _app.websocket_event_loop

    async def spawn_worker_for_library(self, library_name: str, session_id: str) -> None:
        """Spawn a dedicated worker subprocess for the given library.

        The subprocess runs `gtn engine --session-id <ID> --library-name <NAME>` so it
        connects to the current session and loads only the named library.
        """
        if library_name in self._managed_worker_processes:
            logger.debug("Worker for library '%s' already spawned; skipping duplicate spawn.", library_name)
            return

        gtn = shutil.which("gtn")
        if gtn is None:
            msg = "Cannot spawn library worker: 'gtn' not found on PATH."
            raise RuntimeError(msg)

        proc = await asyncio.create_subprocess_exec(
            gtn,
            "engine",
            "--session-id",
            session_id,
            "--library-name",
            library_name,
            env={**os.environ, "GTN_ENGINE_ID": str(uuid.uuid4())},
        )
        self._managed_worker_processes[library_name] = proc
        logger.info("Spawned worker for library '%s' (pid %s)", library_name, proc.pid)

    def on_library_loaded(self, library_info: LibraryManager.LibraryInfo) -> None:
        """Called after each library reaches LOADED state.

        Registered as a callback with LibraryManager. Spawns a dedicated worker
        subprocess for libraries that declare worker.enabled = True.
        """
        if not library_info.requires_worker or not library_info.library_name:
            return
        session_id = self._griptape_nodes.get_session_id()
        if not session_id:
            logger.warning("Cannot spawn worker for library '%s': no active session.", library_info.library_name)
            return
        loop = self._websocket_event_loop
        if loop is None:
            logger.warning(
                "Cannot spawn worker for library '%s': WebSocket event loop not available.",
                library_info.library_name,
            )
            return
        future = asyncio.run_coroutine_threadsafe(
            self.spawn_worker_for_library(library_info.library_name, session_id),
            loop,
        )

        def _log_spawn_error(f: concurrent.futures.Future) -> None:
            exc = f.exception()
            if exc is not None:
                logger.error(
                    "Failed to spawn worker for library '%s': %s",
                    library_info.library_name,
                    exc,
                )

        future.add_done_callback(_log_spawn_error)

    async def route_to_worker(
        self,
        event_request: EventRequest,
        worker_engine_id: str,
        worker_request_topic: str,
    ) -> dict:
        """Forward event_request to the named worker and await the raw result payload.

        Stores a Future keyed by request_id and resolves it when relay_worker_result
        receives the corresponding response. The caller is responsible for deserializing
        the returned dict into the appropriate result type.
        """
        request_id = event_request.request_id or str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict] = loop.create_future()
        self._pending_requests[request_id] = future

        await self.forward_event_to_worker(
            event_request.model_copy(update={"request_id": request_id}),
            worker_engine_id=worker_engine_id,
            worker_request_topic=worker_request_topic,
        )
        try:
            return await asyncio.wait_for(future, timeout=WorkerManager.NODE_EXECUTION_TIMEOUT_S)
        except TimeoutError:
            self._pending_requests.pop(request_id, None)
            msg = f"Worker request timed out after {WorkerManager.NODE_EXECUTION_TIMEOUT_S:.0f}s."
            raise RuntimeError(msg) from None

    async def evict_worker(self, worker_engine_id: str) -> None:
        """Remove a worker from the registry and unsubscribe from its response topic."""
        session_id = self._griptape_nodes.get_session_id()
        self._registered_workers.pop(worker_engine_id, None)
        self._worker_last_seen.pop(worker_engine_id, None)
        lib_name = self._worker_library.get(worker_engine_id)
        self._deregister_worker_library(worker_engine_id)
        topic = f"sessions/{session_id}/workers/{worker_engine_id}/response"
        await self._unsubscribe_from_topic(topic)
        logger.warning("Worker evicted: %s", worker_engine_id)
        # Terminate the managed subprocess for this worker, if any.
        if lib_name:
            proc = self._managed_worker_processes.pop(lib_name, None)
            if proc is not None:
                proc.terminate()
        # Cancel any requests that were awaiting a result from this worker.
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

        # Notify registered callbacks that this worker has been evicted.
        for cb in self._worker_evicted_callbacks:
            try:
                cb(worker_engine_id, lib_name)
            except Exception:
                logger.warning(
                    "Worker-evicted callback raised an exception for worker '%s'", worker_engine_id
                )

    def register_worker_evicted_callback(
        self, callback: Callable[[str, str | None], None]
    ) -> None:
        """Register a callback invoked when a worker is evicted.

        Callbacks are called synchronously in registration order. Exceptions are logged
        but do not prevent other callbacks from running.

        Callback signature: (worker_engine_id: str, library_name: str | None) -> None
        """
        self._worker_evicted_callbacks.append(callback)

    def get_topics_to_subscribe(self, *, is_worker: bool) -> list[str]:
        """Build the list of topics to subscribe to at connection start.

        In worker mode the engine subscribes to its dedicated per-worker request topic.
        In orchestrator mode it subscribes to the session request topic if a session is active.
        """
        topics: list[str] = ["request"]
        engine_id = self._griptape_nodes.get_engine_id()
        if engine_id:
            topics.append(f"engines/{engine_id}/request")

        session_id = self._griptape_nodes.get_session_id()
        if is_worker:
            # Subscribe ONLY to this worker's dedicated per-worker request topic.
            # The orchestrator explicitly routes events here; worker never sees other workers' events.
            topics.append(f"sessions/{session_id}/workers/{engine_id}/request")
        elif session_id:
            topics.append(f"sessions/{session_id}/request")

        return topics

    async def forward_event_to_worker(
        self,
        event: EventRequest,
        *,
        worker_engine_id: str,
        worker_request_topic: str,
    ) -> None:
        """Route an event to the appropriate worker's dedicated request topic.

        MVP: routes to the single registered worker.
        Future: consult a WorkerRegistry to select the correct worker based on event type
        or target library.
        """
        session_id = self._griptape_nodes.get_session_id()
        worker_response_topic = f"sessions/{session_id}/workers/{worker_engine_id}/response"
        forwarded = event.model_copy(update={"response_topic": worker_response_topic})
        logger.debug("Forwarding %s to worker %s", type(event.request).__name__, worker_engine_id)
        await self._send_message("EventRequest", forwarded.json(), worker_request_topic)

    async def relay_worker_result(self, payload: dict) -> None:
        """Relay a result received from a worker back to the GUI session response topic.

        The orchestrator always mediates between workers and the GUI; workers never publish
        directly to the session response topic.
        """
        # Heartbeat responses update the last-seen timestamp but are not forwarded to the GUI.
        # BaseEvent.dict() adds result_type at the outer level (not inside the result dict).
        result_event_type = payload.get("result_type", "")
        if result_event_type == worker_events.WorkerHeartbeatResultSuccess.__name__:
            if m := self._WORKER_RESPONSE_TOPIC_RE.match(payload.get("response_topic", "")):
                worker_engine_id = m.group("worker_engine_id")
                self._worker_last_seen[worker_engine_id] = time.monotonic()
                logger.debug("Heartbeat received from worker %s", worker_engine_id)
            return  # Internal health check — do not forward to GUI

        # Resolve a pending request if a caller is awaiting this result.
        request_id = payload.get("request_id", "")
        if request_id and request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            if not future.done():
                future.set_result(payload)
            return  # Caller owns result handling; do not relay to GUI here.

        # 1 engine = 1 session — the orchestrator's session response topic is always the right target.
        session_response_topic = self._determine_response_topic()
        dest_socket = "success_result" if payload.get("event_type") == "EventResultSuccess" else "failure_result"
        payload["response_topic"] = session_response_topic
        logger.debug("Relaying %s to %s", payload.get("event_type"), session_response_topic)
        await self._send_message(dest_socket, json.dumps(payload), session_response_topic)

    def _determine_response_topic(self) -> str:
        """Determine the response topic based on current session and engine IDs."""
        session_id = self._griptape_nodes.get_session_id()
        if session_id:
            return f"sessions/{session_id}/response"
        engine_id = self._griptape_nodes.get_engine_id()
        if engine_id:
            return f"engines/{engine_id}/response"
        return "response"
