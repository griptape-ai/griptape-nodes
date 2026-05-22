"""Tests for the EventRequestBatch ingest path in `app.py`.

The batch envelope is wire-only: when `_process_api_event` sees one, it should
fan the inner EventRequests out through the same routing the engine uses for
individual frames. Skip-the-line inner requests are awaited inline; the rest
are queued on the EventManager's event queue.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.app import app as app_module
from griptape_nodes.retained_mode.events.app_events import SessionHeartbeatRequest
from griptape_nodes.retained_mode.events.base_events import (
    EventRequest,
    EventRequestBatch,
    SkipTheLineMixin,
)
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest

if TYPE_CHECKING:
    from collections.abc import Iterator

_BATCH_SIZE_2 = 2
_BATCH_SIZE_3 = 3


def _connection_payload(target: str) -> dict:
    """Minimal valid CreateConnectionRequest payload for ingest tests."""
    return {
        "source_parameter_name": "output",
        "target_parameter_name": "text",
        "source_node_name": "Agent_1",
        "target_node_name": target,
    }


def _wire_event_request(request_type: str, payload: dict, request_id: str) -> dict:
    """Build the minimal inner EventRequest dict that `EventRequest.from_dict` accepts."""
    return {
        "event_type": "EventRequest",
        "request_type": request_type,
        "request_id": request_id,
        "response_topic": "sessions/test/response",
        "request": {**payload, "request_id": request_id},
    }


def _wire_batch(*inner: dict) -> dict:
    """Wrap inner EventRequest dicts in the standard API envelope shape."""
    return {"payload": {"event_type": "EventRequestBatch", "requests": list(inner)}}


class TestEventRequestBatchSerialization:
    def test_round_trip_preserves_inner_request_identity(self) -> None:
        """from_dict on a serialized batch reconstructs every inner EventRequest payload."""
        inner_a = _wire_event_request("CreateConnectionRequest", _connection_payload("DisplayText_1"), "req-a")
        inner_b = _wire_event_request("CreateConnectionRequest", _connection_payload("SaveText_1"), "req-b")
        envelope = _wire_batch(inner_a, inner_b)["payload"]

        batch = EventRequestBatch.from_dict(envelope)

        assert isinstance(batch, EventRequestBatch)
        assert len(batch.requests) == _BATCH_SIZE_2
        assert all(isinstance(req, EventRequest) for req in batch.requests)
        assert batch.requests[0].request_id == "req-a"
        assert batch.requests[1].request_id == "req-b"
        assert isinstance(batch.requests[0].request, CreateConnectionRequest)
        assert batch.requests[0].request.target_node_name == "DisplayText_1"

    def test_dict_emits_event_type_and_inner_request_dicts(self) -> None:
        """dict() / json() produce a transport-shaped envelope each consumer can parse."""
        inner = EventRequest(
            request=CreateConnectionRequest(
                source_parameter_name="output",
                target_parameter_name="text",
                source_node_name="Agent_1",
                target_node_name="DisplayText_1",
            ),
            request_id="req-a",
            response_topic="sessions/test/response",
        )
        batch = EventRequestBatch(requests=[inner])

        as_dict = batch.dict()

        assert as_dict["event_type"] == "EventRequestBatch"
        assert isinstance(as_dict["requests"], list)
        assert as_dict["requests"][0]["event_type"] == "EventRequest"
        assert as_dict["requests"][0]["request_type"] == "CreateConnectionRequest"
        # json.loads(json.dumps(...)) sanity-checks that the dict is JSON-clean.
        json.loads(json.dumps(as_dict, default=str))

    def test_get_request_raises(self) -> None:
        """get_request is meaningless on a batch; callers must inspect .requests."""
        batch = EventRequestBatch(requests=[])

        with pytest.raises(NotImplementedError):
            batch.get_request()


class TestProcessApiEventBatchDispatch:
    @pytest.fixture
    def event_manager(self) -> MagicMock:
        """Mock EventManager so we can assert which inner requests landed on the queue."""
        return MagicMock()

    @pytest.fixture(autouse=True)
    def _patched_griptape_nodes(self, event_manager: MagicMock) -> Iterator[None]:
        """Swap `app.griptape_nodes.EventManager()` for a controllable mock."""
        gtn = MagicMock()
        gtn.EventManager.return_value = event_manager
        with patch.object(app_module, "griptape_nodes", gtn):
            yield

    @pytest.mark.asyncio
    async def test_batch_with_normal_requests_queues_each_inner_request(self, event_manager: MagicMock) -> None:
        """Non-skip-the-line inner requests are queued individually for `_process_event_queue`."""
        envelope = _wire_batch(
            _wire_event_request("CreateConnectionRequest", _connection_payload("DisplayText_1"), "1"),
            _wire_event_request("CreateConnectionRequest", _connection_payload("SaveText_1"), "2"),
            _wire_event_request("CreateConnectionRequest", _connection_payload("PrintText_1"), "3"),
        )

        await app_module._process_api_event(envelope)

        assert event_manager.put_event.call_count == _BATCH_SIZE_3
        queued = [call.args[0] for call in event_manager.put_event.call_args_list]
        assert all(isinstance(ev, EventRequest) for ev in queued)
        assert [ev.request_id for ev in queued] == ["1", "2", "3"]

    @pytest.mark.asyncio
    async def test_batch_with_skip_the_line_inner_requests_runs_inline(self, event_manager: MagicMock) -> None:
        """Inner requests implementing SkipTheLineMixin bypass the queue and run immediately."""
        envelope = _wire_batch(
            _wire_event_request("CreateConnectionRequest", _connection_payload("DisplayText_1"), "q"),
            _wire_event_request("SessionHeartbeatRequest", {}, "s"),
        )

        # Sanity-check that SessionHeartbeatRequest still represents skip-the-line behavior
        # so this test stays meaningful as the registry evolves.
        assert issubclass(SessionHeartbeatRequest, SkipTheLineMixin)

        with patch.object(app_module, "_process_event_request", new=AsyncMock()) as inline:
            await app_module._process_api_event(envelope)

        # Skip-the-line went inline, normal request was queued.
        assert inline.await_count == 1
        assert inline.await_args is not None
        inline_event = inline.await_args.args[0]
        assert isinstance(inline_event, EventRequest)
        assert inline_event.request_id == "s"

        assert event_manager.put_event.call_count == 1
        queued_event = event_manager.put_event.call_args.args[0]
        assert queued_event.request_id == "q"

    @pytest.mark.asyncio
    async def test_empty_batch_is_a_noop(self, event_manager: MagicMock) -> None:
        """An empty batch is valid and dispatches nothing."""
        await app_module._process_api_event({"payload": {"event_type": "EventRequestBatch", "requests": []}})

        event_manager.put_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_individual_event_request_still_dispatches(self, event_manager: MagicMock) -> None:
        """Existing non-batch EventRequest frames continue to flow through the same path."""
        single = _wire_event_request("CreateConnectionRequest", _connection_payload("DisplayText_1"), "solo")

        await app_module._process_api_event({"payload": single})

        assert event_manager.put_event.call_count == 1
        queued = event_manager.put_event.call_args.args[0]
        assert isinstance(queued, EventRequest)
        assert queued.request_id == "solo"
