"""Tests for WorkerManager.

Covers registration, heartbeat, eviction, unregistration, and the relay
filter that keeps internal health-check results off the GUI topic.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from griptape_nodes.app.worker_manager import WorkerManager
from griptape_nodes.retained_mode.events import worker_events

_SESSION = "sess-abc"
_ENGINE = "eng-xyz"
_WORKER_REQUEST_TOPIC = f"sessions/{_SESSION}/workers/{_ENGINE}/request"
_WORKER_RESPONSE_TOPIC = f"sessions/{_SESSION}/workers/{_ENGINE}/response"


@pytest.fixture
def worker_manager() -> WorkerManager:
    """Construct a WorkerManager with AsyncMock transport callables for isolated testing."""
    gtn = MagicMock()
    gtn.get_session_id.return_value = _SESSION
    gtn.get_engine_id.return_value = _ENGINE
    return WorkerManager(
        griptape_nodes=gtn,
        event_manager=MagicMock(),
        ws_outgoing_queue=asyncio.Queue(),
        send_message=AsyncMock(),
        subscribe_to_topic=AsyncMock(),
        unsubscribe_from_topic=AsyncMock(),
    )


class TestHandleRegisterWorkerRequest:
    @pytest.mark.asyncio
    async def test_adds_worker_to_registered_workers(self, worker_manager: WorkerManager) -> None:
        request = worker_events.RegisterWorkerRequest(worker_engine_id=_ENGINE)

        await worker_manager.handle_register_worker_request(request)

        assert _ENGINE in worker_manager._registered_workers
        assert worker_manager._registered_workers[_ENGINE] == _WORKER_REQUEST_TOPIC

    @pytest.mark.asyncio
    async def test_seeds_last_seen_timestamp(self, worker_manager: WorkerManager) -> None:
        request = worker_events.RegisterWorkerRequest(worker_engine_id=_ENGINE)

        await worker_manager.handle_register_worker_request(request)

        assert _ENGINE in worker_manager._worker_last_seen
        assert worker_manager._worker_last_seen[_ENGINE] > 0

    @pytest.mark.asyncio
    async def test_subscribes_to_worker_response_topic(self, worker_manager: WorkerManager) -> None:
        request = worker_events.RegisterWorkerRequest(worker_engine_id=_ENGINE)

        await worker_manager.handle_register_worker_request(request)

        worker_manager._subscribe_to_topic.assert_called_once_with(_WORKER_RESPONSE_TOPIC)  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_returns_success_with_engine_id(self, worker_manager: WorkerManager) -> None:
        request = worker_events.RegisterWorkerRequest(worker_engine_id=_ENGINE)

        result = await worker_manager.handle_register_worker_request(request)

        assert isinstance(result, worker_events.RegisterWorkerResultSuccess)
        assert result.worker_engine_id == _ENGINE


class TestHandleWorkerHeartbeatRequest:
    def test_returns_success_echoing_heartbeat_id(self, worker_manager: WorkerManager) -> None:
        request = worker_events.WorkerHeartbeatRequest(heartbeat_id="hb-001")

        result = worker_manager.handle_worker_heartbeat_request(request)

        assert isinstance(result, worker_events.WorkerHeartbeatResultSuccess)
        assert result.heartbeat_id == "hb-001"

    def test_updates_last_received_timestamp(self, worker_manager: WorkerManager) -> None:
        worker_manager._worker_heartbeat_last_received_at = 0.0
        request = worker_events.WorkerHeartbeatRequest(heartbeat_id="hb-002")

        worker_manager.handle_worker_heartbeat_request(request)

        assert worker_manager._worker_heartbeat_last_received_at > 0.0


class TestWorkerHeartbeatMonitor:
    @pytest.mark.asyncio
    async def test_raises_after_timeout(self, worker_manager: WorkerManager, monkeypatch: pytest.MonkeyPatch) -> None:
        """Monitor raises RuntimeError when no heartbeat arrives within the timeout."""
        monkeypatch.setattr(WorkerManager, "HEARTBEAT_INTERVAL_S", 0.01)
        monkeypatch.setattr(WorkerManager, "HEARTBEAT_TIMEOUT_S", 0.0)
        worker_manager._worker_heartbeat_last_received_at = 0.0

        with pytest.raises(RuntimeError, match="Orchestrator heartbeat lost"):
            await worker_manager.worker_heartbeat_monitor()

    @pytest.mark.asyncio
    async def test_does_not_raise_while_heartbeats_arrive(
        self, worker_manager: WorkerManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Monitor does not raise when the timestamp is kept current."""
        monkeypatch.setattr(WorkerManager, "HEARTBEAT_INTERVAL_S", 0.01)
        monkeypatch.setattr(WorkerManager, "HEARTBEAT_TIMEOUT_S", 60.0)

        task = asyncio.create_task(worker_manager.worker_heartbeat_monitor())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class TestHandleUnregisterWorkerRequest:
    @pytest.mark.asyncio
    async def test_removes_worker_from_registered_workers(self, worker_manager: WorkerManager) -> None:
        worker_manager._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        worker_manager._worker_last_seen[_ENGINE] = 999.0

        request = worker_events.UnregisterWorkerRequest(worker_engine_id=_ENGINE)
        await worker_manager.handle_unregister_worker_request(request)

        assert _ENGINE not in worker_manager._registered_workers

    @pytest.mark.asyncio
    async def test_removes_worker_from_last_seen(self, worker_manager: WorkerManager) -> None:
        worker_manager._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        worker_manager._worker_last_seen[_ENGINE] = 999.0

        request = worker_events.UnregisterWorkerRequest(worker_engine_id=_ENGINE)
        await worker_manager.handle_unregister_worker_request(request)

        assert _ENGINE not in worker_manager._worker_last_seen

    @pytest.mark.asyncio
    async def test_unsubscribes_from_worker_response_topic(self, worker_manager: WorkerManager) -> None:
        worker_manager._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        worker_manager._worker_last_seen[_ENGINE] = 999.0

        request = worker_events.UnregisterWorkerRequest(worker_engine_id=_ENGINE)
        await worker_manager.handle_unregister_worker_request(request)

        worker_manager._unsubscribe_from_topic.assert_called_once_with(_WORKER_RESPONSE_TOPIC)  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_returns_success_with_engine_id(self, worker_manager: WorkerManager) -> None:
        worker_manager._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        worker_manager._worker_last_seen[_ENGINE] = 999.0

        request = worker_events.UnregisterWorkerRequest(worker_engine_id=_ENGINE)
        result = await worker_manager.handle_unregister_worker_request(request)

        assert isinstance(result, worker_events.UnregisterWorkerResultSuccess)
        assert result.worker_engine_id == _ENGINE

    @pytest.mark.asyncio
    async def test_tolerates_unknown_worker(self, worker_manager: WorkerManager) -> None:
        """Unregistering a worker that is not in the registry must not raise."""
        request = worker_events.UnregisterWorkerRequest(worker_engine_id="ghost-engine")

        result = await worker_manager.handle_unregister_worker_request(request)

        assert isinstance(result, worker_events.UnregisterWorkerResultSuccess)


class TestRelayWorkerResult:
    @pytest.mark.asyncio
    async def test_heartbeat_success_updates_last_seen(self, worker_manager: WorkerManager) -> None:
        # result_type lives at the outer level — set by BaseEvent.dict(), not inside result{}
        payload = {
            "event_type": "EventResultSuccess",
            "result_type": worker_events.WorkerHeartbeatResultSuccess.__name__,
            "result": {"heartbeat_id": "hb-1"},
            "response_topic": _WORKER_RESPONSE_TOPIC,
        }

        await worker_manager.relay_worker_result(payload)

        worker_manager._send_message.assert_not_called()  # type: ignore[union-attr]
        assert _ENGINE in worker_manager._worker_last_seen

    @pytest.mark.asyncio
    async def test_heartbeat_with_malformed_topic_does_not_crash(self, worker_manager: WorkerManager) -> None:
        payload = {
            "event_type": "EventResultSuccess",
            "result_type": worker_events.WorkerHeartbeatResultSuccess.__name__,
            "result": {"heartbeat_id": "hb-1"},
            "response_topic": "bad/topic",
        }

        await worker_manager.relay_worker_result(payload)

        worker_manager._send_message.assert_not_called()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_non_heartbeat_result_is_forwarded_to_gui(self, worker_manager: WorkerManager) -> None:
        payload = {
            "event_type": "EventResultSuccess",
            "result_type": "SomeOtherResultSuccess",
            "result": {},
            "response_topic": _WORKER_RESPONSE_TOPIC,
        }

        await worker_manager.relay_worker_result(payload)

        worker_manager._send_message.assert_called_once()  # type: ignore[union-attr]


class TestEvictWorker:
    @pytest.mark.asyncio
    async def test_removes_worker_from_state(self, worker_manager: WorkerManager) -> None:
        worker_manager._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        worker_manager._worker_last_seen[_ENGINE] = 100.0

        await worker_manager.evict_worker(_ENGINE)

        assert _ENGINE not in worker_manager._registered_workers
        assert _ENGINE not in worker_manager._worker_last_seen

    @pytest.mark.asyncio
    async def test_calls_unsubscribe_for_response_topic(self, worker_manager: WorkerManager) -> None:
        worker_manager._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        worker_manager._worker_last_seen[_ENGINE] = 100.0

        await worker_manager.evict_worker(_ENGINE)

        worker_manager._unsubscribe_from_topic.assert_called_once_with(_WORKER_RESPONSE_TOPIC)  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_tolerates_unknown_worker(self, worker_manager: WorkerManager) -> None:
        """Evicting a worker not in the registry must not raise."""
        await worker_manager.evict_worker("ghost-engine")
