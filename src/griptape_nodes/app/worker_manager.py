from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from typing import TYPE_CHECKING

from griptape_nodes.bootstrap.utils.subprocess_websocket_base import WebSocketMessage
from griptape_nodes.retained_mode.events import worker_events
from griptape_nodes.retained_mode.events.base_events import EventRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.settings import (
    WORKER_HEARTBEAT_INTERVAL_KEY,
    WORKER_HEARTBEAT_TIMEOUT_KEY,
    WORKER_NODE_EXECUTION_TIMEOUT_KEY,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from griptape_nodes.api_client.request_client import RequestClient
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes_app")


class WorkerManager:
    """Manages worker registration, heartbeating, eviction, and event routing.

    Encapsulates all state and logic related to worker engines on both the
    orchestrator side (registry, heartbeat challenges, eviction, result relay)
    and the worker side (heartbeat response, self-termination monitor).

    Transport operations (subscribe, unsubscribe, send message) are injected
    as callables so this class has no direct dependency on WebSocket plumbing.
    """

    DEFAULT_HEARTBEAT_INTERVAL_S: float = 5.0
    DEFAULT_HEARTBEAT_TIMEOUT_S: float = 15.0
    DEFAULT_NODE_EXECUTION_TIMEOUT_S: float = 300.0

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
        request_client: RequestClient,
    ) -> None:
        self._griptape_nodes = griptape_nodes
        self._ws_outgoing_queue = ws_outgoing_queue
        self._send_message = send_message
        self._subscribe_to_topic = subscribe_to_topic
        self._unsubscribe_from_topic = unsubscribe_from_topic
        self._request_client = request_client

        # Orchestrator-side registry: worker_engine_id → worker request topic
        self._registered_workers: dict[str, str] = {}

        # Orchestrator-side: worker_key → list of (engine_id, request_topic) tuples.
        # Today: at most one entry per key. Future: N workers per key.
        self._keyed_workers: dict[str, list[tuple[str, str]]] = {}

        # Orchestrator-side reverse lookup: worker_engine_id → worker_key (or None for general workers)
        self._worker_key: dict[str, str | None] = {}

        # Subprocesses spawned by this orchestrator (library_name → process)
        self._managed_worker_processes: dict[str, asyncio.subprocess.Process] = {}

        # Orchestrator-side: worker_engine_id → monotonic timestamp of last heartbeat response
        self._worker_last_seen: dict[str, float] = {}

        # Worker-side: monotonic timestamp of last heartbeat received from the orchestrator
        self._worker_heartbeat_last_received_at: float = 0.0

        # Callbacks invoked when a worker is evicted: (worker_engine_id, library_name | None)
        self._worker_evicted_callbacks: list[Callable[[str, str | None], None]] = []

        config = GriptapeNodes.ConfigManager()
        self.HEARTBEAT_INTERVAL_S: float = config.get_config_value(
            WORKER_HEARTBEAT_INTERVAL_KEY, default=WorkerManager.DEFAULT_HEARTBEAT_INTERVAL_S, cast_type=float
        )
        self.HEARTBEAT_TIMEOUT_S: float = config.get_config_value(
            WORKER_HEARTBEAT_TIMEOUT_KEY, default=WorkerManager.DEFAULT_HEARTBEAT_TIMEOUT_S, cast_type=float
        )
        self.NODE_EXECUTION_TIMEOUT_S: float = config.get_config_value(
            WORKER_NODE_EXECUTION_TIMEOUT_KEY, default=WorkerManager.DEFAULT_NODE_EXECUTION_TIMEOUT_S, cast_type=float
        )

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

        # Track worker key association for routing.
        self._worker_key[wid] = request.library_name
        if request.library_name:
            self._keyed_workers.setdefault(request.library_name, []).append((wid, request_topic))
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
        lib_name = self._worker_key.get(wid)
        self._deregister_worker_key(wid)
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
            await asyncio.sleep(self.HEARTBEAT_INTERVAL_S)
            if not self._registered_workers:
                continue

            now = time.monotonic()
            stale = [
                wid
                for wid in list(self._registered_workers)
                if now - self._worker_last_seen.get(wid, 0) > self.HEARTBEAT_TIMEOUT_S
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
            await asyncio.sleep(self.HEARTBEAT_INTERVAL_S)
            elapsed = time.monotonic() - self._worker_heartbeat_last_received_at
            if elapsed > self.HEARTBEAT_TIMEOUT_S:
                msg = f"Orchestrator heartbeat lost ({elapsed:.1f}s since last heartbeat); worker is shutting down."
                logger.warning(msg)
                raise RuntimeError(msg)

    def get_active_worker(self) -> tuple[str, str] | None:
        """Return (worker_engine_id, worker_request_topic) for the registered worker, or None."""
        return next(iter(self._registered_workers.items()), None)

    def get_worker_for_key(self, key: str) -> tuple[str, str] | None:
        """Return (worker_engine_id, worker_request_topic) for a worker registered under key, or None.

        Today returns the first registered worker for the key. Future versions can
        load-balance across multiple workers for the same key.
        """
        workers = self._keyed_workers.get(key, [])
        return workers[0] if workers else None

    def _deregister_worker_key(self, worker_engine_id: str) -> None:
        """Remove a worker from the routing tables."""
        key = self._worker_key.pop(worker_engine_id, None)
        if key and key in self._keyed_workers:
            self._keyed_workers[key] = [
                (eid, topic) for eid, topic in self._keyed_workers[key] if eid != worker_engine_id
            ]
            if not self._keyed_workers[key]:
                del self._keyed_workers[key]

    async def spawn_worker(self, args: list[str], worker_key: str) -> None:
        """Spawn a worker subprocess using the given command args.

        worker_key is an opaque identifier used to track the process and prevent
        duplicate spawns. Callers are responsible for constructing the args list.
        """
        if worker_key in self._managed_worker_processes:
            logger.debug("Worker for key '%s' already spawned; skipping duplicate spawn.", worker_key)
            return
        proc = await asyncio.create_subprocess_exec(*args, env={**os.environ, "GTN_ENGINE_ID": str(uuid.uuid4())})
        self._managed_worker_processes[worker_key] = proc
        logger.info("Spawned worker for key '%s' (pid %s)", worker_key, proc.pid)

    def terminate_managed_workers(self) -> None:
        """Terminate all worker subprocesses spawned by this orchestrator.

        Called on orchestrator shutdown to prevent orphan processes.
        Best-effort: each process is signalled with SIGTERM; already-exited
        processes are silently ignored.
        """
        for library_name, proc in list(self._managed_worker_processes.items()):
            try:
                proc.terminate()
                logger.debug("Terminated worker process for library '%s' (pid %s)", library_name, proc.pid)
            except ProcessLookupError:
                logger.debug("Worker process for library '%s' already exited", library_name)
        self._managed_worker_processes.clear()

    async def route_to_worker(
        self,
        event_request: EventRequest,
        worker_engine_id: str,
        worker_request_topic: str,
    ) -> dict:
        """Forward event_request to the named worker and await the raw result payload.

        Registers a Future via RequestClient keyed by request_id and resolves it when
        the worker response arrives. The caller is responsible for deserializing the
        returned dict into the appropriate result type.
        """
        request_id = event_request.request_id or str(uuid.uuid4())
        future = await self._request_client.track_request(request_id, tag=worker_engine_id)

        await self.forward_event_to_worker(
            event_request.model_copy(update={"request_id": request_id}),
            worker_engine_id=worker_engine_id,
            worker_request_topic=worker_request_topic,
        )
        try:
            return await asyncio.wait_for(future, timeout=self.NODE_EXECUTION_TIMEOUT_S)
        except TimeoutError:
            msg = f"Worker request timed out after {self.NODE_EXECUTION_TIMEOUT_S:.0f}s."
            raise RuntimeError(msg) from None

    async def evict_worker(self, worker_engine_id: str) -> None:
        """Remove a worker from the registry and unsubscribe from its response topic."""
        session_id = self._griptape_nodes.get_session_id()
        self._registered_workers.pop(worker_engine_id, None)
        self._worker_last_seen.pop(worker_engine_id, None)
        lib_name = self._worker_key.get(worker_engine_id)
        self._deregister_worker_key(worker_engine_id)
        topic = f"sessions/{session_id}/workers/{worker_engine_id}/response"
        await self._unsubscribe_from_topic(topic)
        logger.warning("Worker evicted: %s", worker_engine_id)
        # Terminate the managed subprocess for this worker, if any.
        if lib_name:
            proc = self._managed_worker_processes.pop(lib_name, None)
            if proc is not None:
                proc.terminate()
        # Cancel any requests that were awaiting a result from this worker.
        await self._request_client.cancel_requests_by_tag(worker_engine_id)

        # Notify registered callbacks that this worker has been evicted.
        for cb in self._worker_evicted_callbacks:
            try:
                cb(worker_engine_id, lib_name)
            except Exception:
                logger.warning("Worker-evicted callback raised an exception for worker '%s'", worker_engine_id)

    def register_worker_evicted_callback(self, callback: Callable[[str, str | None], None]) -> None:
        """Register a callback invoked when a worker is evicted.

        Callbacks are called synchronously in registration order. Exceptions are logged
        but do not prevent other callbacks from running.

        Callback signature: (worker_engine_id: str, library_name: str | None) -> None
        """
        self._worker_evicted_callbacks.append(callback)

    def get_topics_to_subscribe(self, *, is_worker: bool) -> list[str]:
        """Build the list of topics to subscribe to at connection start.

        In worker mode the engine subscribes only to its dedicated per-worker request topic
        and its direct-target engine topic. Workers must NOT subscribe to the generic "request"
        topic, which is where the MCP server broadcasts; doing so causes workers to handle
        requests intended for the orchestrator.

        In orchestrator mode it subscribes to the generic "request" topic (MCP/API entry point)
        and the session request topic.
        """
        engine_id = self._griptape_nodes.get_engine_id()
        session_id = self._griptape_nodes.get_session_id()

        topics: list[str] = []
        if engine_id:
            topics.append(f"engines/{engine_id}/request")

        if is_worker:
            # Subscribe ONLY to this worker's dedicated per-worker request topic.
            # The orchestrator explicitly routes events here; worker never sees other workers' events.
            if session_id and engine_id:
                topics.append(f"sessions/{session_id}/workers/{engine_id}/request")
        else:
            # Orchestrator handles all broadcast requests from the MCP server and the GUI.
            topics.append("request")
            if session_id:
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
        """Relay an unmatched worker result to the GUI session response topic.

        Called by the unhandled_handler for worker result messages that were not
        resolved by RequestClient (heartbeats and any results without a pending request).
        The orchestrator always mediates between workers and the GUI; workers never
        publish directly to the session response topic.
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
