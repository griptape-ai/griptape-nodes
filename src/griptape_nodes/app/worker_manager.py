from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import TYPE_CHECKING

from griptape_nodes.bootstrap.utils.subprocess_websocket_base import WebSocketMessage
from griptape_nodes.retained_mode.events import app_events, worker_events
from griptape_nodes.retained_mode.events.base_events import EventRequest

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
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

    HEARTBEAT_INTERVAL_S: float = 5.0
    HEARTBEAT_TIMEOUT_S: float = 15.0

    _WORKER_RESPONSE_TOPIC_RE: re.Pattern = re.compile(r"sessions/[^/]+/workers/(?P<worker_engine_id>[^/]+)/response$")

    LOCAL_REQUEST_TYPES: tuple[type, ...] = (
        app_events.AppStartSessionRequest,
        app_events.AppEndSessionRequest,
        app_events.AppGetSessionRequest,
        app_events.SessionHeartbeatRequest,
        app_events.EngineHeartbeatRequest,
        worker_events.RegisterWorkerRequest,
        worker_events.WorkerHeartbeatRequest,
        worker_events.UnregisterWorkerRequest,
    )

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
        # MVP: at most one entry. Future: WorkerRegistry with library→worker routing.
        self._registered_workers: dict[str, str] = {}

        # Orchestrator-side: worker_engine_id → monotonic timestamp of last heartbeat response
        self._worker_last_seen: dict[str, float] = {}

        # Worker-side: monotonic timestamp of last heartbeat received from the orchestrator
        self._worker_heartbeat_last_received_at: float = 0.0

        event_manager.assign_manager_to_request_type(
            worker_events.RegisterWorkerRequest, self.handle_register_worker_request
        )
        event_manager.assign_manager_to_request_type(
            worker_events.WorkerHeartbeatRequest, self.handle_worker_heartbeat_request
        )
        event_manager.assign_manager_to_request_type(
            worker_events.UnregisterWorkerRequest, self.handle_unregister_worker_request
        )

    # -------------------------------------------------------------------------
    # Event handlers
    # -------------------------------------------------------------------------

    async def handle_register_worker_request(
        self,
        request: worker_events.RegisterWorkerRequest,
    ) -> worker_events.RegisterWorkerResultSuccess | worker_events.RegisterWorkerResultFailure:
        """Handle a worker registration request from a worker engine."""
        wid = request.worker_engine_id
        session_id = self._griptape_nodes.get_session_id()
        self._registered_workers[wid] = f"sessions/{session_id}/workers/{wid}/request"
        self._worker_last_seen[wid] = time.monotonic()
        response_topic = f"sessions/{session_id}/workers/{wid}/response"
        await self._subscribe_to_topic(response_topic)
        logger.info("Worker registered: %s (session %s)", wid, session_id)
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
        response_topic = f"sessions/{session_id}/workers/{wid}/response"
        await self._unsubscribe_from_topic(response_topic)
        logger.info("Worker unregistered: %s", wid)
        return worker_events.UnregisterWorkerResultSuccess(worker_engine_id=wid, result_details="Worker unregistered.")

    # -------------------------------------------------------------------------
    # Orchestrator async tasks
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Worker async tasks
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Registry helpers
    # -------------------------------------------------------------------------

    def get_active_worker(self) -> tuple[str, str] | None:
        """Return (worker_engine_id, worker_request_topic) for the registered worker, or None."""
        return next(iter(self._registered_workers.items()), None)

    async def evict_worker(self, worker_engine_id: str) -> None:
        """Remove a worker from the registry and unsubscribe from its response topic."""
        session_id = self._griptape_nodes.get_session_id()
        self._registered_workers.pop(worker_engine_id, None)
        self._worker_last_seen.pop(worker_engine_id, None)
        topic = f"sessions/{session_id}/workers/{worker_engine_id}/response"
        await self._unsubscribe_from_topic(topic)
        logger.warning("Worker evicted: %s", worker_engine_id)

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

    # -------------------------------------------------------------------------
    # Event routing
    # -------------------------------------------------------------------------

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

        # 1 engine = 1 session — the orchestrator's session response topic is always the right target.
        session_response_topic = self._determine_response_topic()
        dest_socket = "success_result" if payload.get("event_type") == "EventResultSuccess" else "failure_result"
        payload["response_topic"] = session_response_topic
        logger.debug("Relaying %s to %s", payload.get("event_type"), session_response_topic)
        await self._send_message(dest_socket, json.dumps(payload), session_response_topic)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _determine_response_topic(self) -> str:
        """Determine the response topic based on current session and engine IDs."""
        session_id = self._griptape_nodes.get_session_id()
        if session_id:
            return f"sessions/{session_id}/response"
        engine_id = self._griptape_nodes.get_engine_id()
        if engine_id:
            return f"engines/{engine_id}/response"
        return "response"
