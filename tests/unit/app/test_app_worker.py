"""Tests for worker-engine functions in app.py.

Covers registration, heartbeat, eviction, unregistration, and the relay
filter that keeps internal health-check results off the GUI topic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from collections.abc import Generator

import pytest

import griptape_nodes.app.app as app_module
from griptape_nodes.app.app import UnsubscribeCommand
from griptape_nodes.retained_mode.events import worker_events

_SESSION = "sess-abc"
_ENGINE = "eng-xyz"
_WORKER_REQUEST_TOPIC = f"sessions/{_SESSION}/workers/{_ENGINE}/request"
_WORKER_RESPONSE_TOPIC = f"sessions/{_SESSION}/workers/{_ENGINE}/response"


@pytest.fixture(autouse=True)
def _reset_worker_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace module-level worker dicts with fresh copies for each test."""
    monkeypatch.setattr(app_module, "_registered_workers", {})
    monkeypatch.setattr(app_module, "_worker_last_seen", {})


@pytest.fixture
def _mock_session_id() -> Generator[None, None, None]:
    with patch.object(app_module.griptape_nodes, "get_session_id", return_value=_SESSION):
        yield


@pytest.mark.usefixtures("_mock_session_id")
class TestHandleRegisterWorkerRequest:
    @pytest.mark.asyncio
    async def test_adds_worker_to_registered_workers(self) -> None:
        request = worker_events.RegisterWorkerRequest(worker_engine_id=_ENGINE)

        with patch("griptape_nodes.app.app._subscribe_to_topic", new_callable=AsyncMock):
            await app_module._handle_register_worker_request(request)

        assert _ENGINE in app_module._registered_workers
        assert app_module._registered_workers[_ENGINE] == _WORKER_REQUEST_TOPIC

    @pytest.mark.asyncio
    async def test_seeds_last_seen_timestamp(self) -> None:
        request = worker_events.RegisterWorkerRequest(worker_engine_id=_ENGINE)

        with patch("griptape_nodes.app.app._subscribe_to_topic", new_callable=AsyncMock):
            await app_module._handle_register_worker_request(request)

        assert _ENGINE in app_module._worker_last_seen
        assert app_module._worker_last_seen[_ENGINE] > 0

    @pytest.mark.asyncio
    async def test_subscribes_to_worker_response_topic(self) -> None:
        request = worker_events.RegisterWorkerRequest(worker_engine_id=_ENGINE)

        with patch("griptape_nodes.app.app._subscribe_to_topic", new_callable=AsyncMock) as mock_sub:
            await app_module._handle_register_worker_request(request)

        mock_sub.assert_called_once_with(_WORKER_RESPONSE_TOPIC)

    @pytest.mark.asyncio
    async def test_returns_success_with_engine_id(self) -> None:
        request = worker_events.RegisterWorkerRequest(worker_engine_id=_ENGINE)

        with patch("griptape_nodes.app.app._subscribe_to_topic", new_callable=AsyncMock):
            result = await app_module._handle_register_worker_request(request)

        assert isinstance(result, worker_events.RegisterWorkerResultSuccess)
        assert result.worker_engine_id == _ENGINE


class TestHandleWorkerHeartbeatRequest:
    def test_returns_success_echoing_heartbeat_id(self) -> None:
        request = worker_events.WorkerHeartbeatRequest(heartbeat_id="hb-001")

        result = app_module._handle_worker_heartbeat_request(request)

        assert isinstance(result, worker_events.WorkerHeartbeatResultSuccess)
        assert result.heartbeat_id == "hb-001"


@pytest.mark.usefixtures("_mock_session_id")
class TestHandleUnregisterWorkerRequest:
    @pytest.mark.asyncio
    async def test_removes_worker_from_registered_workers(self) -> None:
        app_module._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        app_module._worker_last_seen[_ENGINE] = 999.0

        request = worker_events.UnregisterWorkerRequest(worker_engine_id=_ENGINE)
        with patch("griptape_nodes.app.app._unsubscribe_from_topic", new_callable=AsyncMock):
            await app_module._handle_unregister_worker_request(request)

        assert _ENGINE not in app_module._registered_workers

    @pytest.mark.asyncio
    async def test_removes_worker_from_last_seen(self) -> None:
        app_module._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        app_module._worker_last_seen[_ENGINE] = 999.0

        request = worker_events.UnregisterWorkerRequest(worker_engine_id=_ENGINE)
        with patch("griptape_nodes.app.app._unsubscribe_from_topic", new_callable=AsyncMock):
            await app_module._handle_unregister_worker_request(request)

        assert _ENGINE not in app_module._worker_last_seen

    @pytest.mark.asyncio
    async def test_unsubscribes_from_worker_response_topic(self) -> None:
        app_module._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        app_module._worker_last_seen[_ENGINE] = 999.0

        request = worker_events.UnregisterWorkerRequest(worker_engine_id=_ENGINE)
        with patch("griptape_nodes.app.app._unsubscribe_from_topic", new_callable=AsyncMock) as mock_unsub:
            await app_module._handle_unregister_worker_request(request)

        mock_unsub.assert_called_once_with(_WORKER_RESPONSE_TOPIC)

    @pytest.mark.asyncio
    async def test_returns_success_with_engine_id(self) -> None:
        app_module._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        app_module._worker_last_seen[_ENGINE] = 999.0

        request = worker_events.UnregisterWorkerRequest(worker_engine_id=_ENGINE)
        with patch("griptape_nodes.app.app._unsubscribe_from_topic", new_callable=AsyncMock):
            result = await app_module._handle_unregister_worker_request(request)

        assert isinstance(result, worker_events.UnregisterWorkerResultSuccess)
        assert result.worker_engine_id == _ENGINE

    @pytest.mark.asyncio
    async def test_tolerates_unknown_worker(self) -> None:
        """Unregistering a worker that is not in the registry must not raise."""
        request = worker_events.UnregisterWorkerRequest(worker_engine_id="ghost-engine")

        with patch("griptape_nodes.app.app._unsubscribe_from_topic", new_callable=AsyncMock):
            result = await app_module._handle_unregister_worker_request(request)

        assert isinstance(result, worker_events.UnregisterWorkerResultSuccess)


class TestRelayWorkerResult:
    @pytest.mark.asyncio
    async def test_heartbeat_success_updates_last_seen(self) -> None:
        # result_type lives at the outer level — set by BaseEvent.dict(), not inside result{}
        payload = {
            "event_type": "EventResultSuccess",
            "result_type": worker_events.WorkerHeartbeatResultSuccess.__name__,
            "result": {"heartbeat_id": "hb-1"},
            "response_topic": _WORKER_RESPONSE_TOPIC,
        }

        with patch("griptape_nodes.app.app._send_message", new_callable=AsyncMock) as mock_send:
            await app_module._relay_worker_result(payload)

        mock_send.assert_not_called()
        assert _ENGINE in app_module._worker_last_seen

    @pytest.mark.asyncio
    async def test_heartbeat_with_malformed_topic_does_not_crash(self) -> None:
        payload = {
            "event_type": "EventResultSuccess",
            "result_type": worker_events.WorkerHeartbeatResultSuccess.__name__,
            "result": {"heartbeat_id": "hb-1"},
            "response_topic": "bad/topic",
        }

        with patch("griptape_nodes.app.app._send_message", new_callable=AsyncMock) as mock_send:
            await app_module._relay_worker_result(payload)

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_heartbeat_result_is_forwarded_to_gui(self) -> None:
        payload = {
            "event_type": "EventResultSuccess",
            "result_type": "SomeOtherResultSuccess",
            "result": {},
            "response_topic": _WORKER_RESPONSE_TOPIC,
        }

        with (
            patch("griptape_nodes.app.app._send_message", new_callable=AsyncMock) as mock_send,
            patch.object(app_module.griptape_nodes, "get_session_id", return_value=_SESSION),
        ):
            await app_module._relay_worker_result(payload)

        mock_send.assert_called_once()


class TestEvictWorker:
    @pytest.mark.asyncio
    async def test_removes_worker_from_state(self) -> None:
        app_module._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        app_module._worker_last_seen[_ENGINE] = 100.0

        with (
            patch.object(app_module.griptape_nodes, "get_session_id", return_value=_SESSION),
            patch.object(app_module.ws_outgoing_queue, "put", new_callable=AsyncMock),
        ):
            await app_module._evict_worker(_ENGINE)

        assert _ENGINE not in app_module._registered_workers
        assert _ENGINE not in app_module._worker_last_seen

    @pytest.mark.asyncio
    async def test_queues_unsubscribe_command(self) -> None:
        app_module._registered_workers[_ENGINE] = _WORKER_REQUEST_TOPIC
        app_module._worker_last_seen[_ENGINE] = 100.0

        with (
            patch.object(app_module.griptape_nodes, "get_session_id", return_value=_SESSION),
            patch.object(app_module.ws_outgoing_queue, "put", new_callable=AsyncMock) as mock_put,
        ):
            await app_module._evict_worker(_ENGINE)

        mock_put.assert_called_once()
        cmd = mock_put.call_args[0][0]
        assert isinstance(cmd, UnsubscribeCommand)
        assert cmd.topic == _WORKER_RESPONSE_TOPIC

    @pytest.mark.asyncio
    async def test_tolerates_unknown_worker(self) -> None:
        """Evicting a worker not in the registry must not raise."""
        with (
            patch.object(app_module.griptape_nodes, "get_session_id", return_value=_SESSION),
            patch.object(app_module.ws_outgoing_queue, "put", new_callable=AsyncMock),
        ):
            await app_module._evict_worker("ghost-engine")
