"""Tests for worker event payloads."""

from griptape_nodes.retained_mode.events.base_events import SkipTheLineMixin
from griptape_nodes.retained_mode.events.worker_events import (
    RegisterWorkerRequest,
    RegisterWorkerResultFailure,
    RegisterWorkerResultSuccess,
    UnregisterWorkerRequest,
    UnregisterWorkerResultFailure,
    UnregisterWorkerResultSuccess,
    WorkerHeartbeatRequest,
    WorkerHeartbeatResultSuccess,
)


class TestRegisterWorkerEvents:
    def test_request_stores_engine_id(self) -> None:
        request = RegisterWorkerRequest(worker_engine_id="eng-1")

        assert request.worker_engine_id == "eng-1"

    def test_result_success_stores_engine_id(self) -> None:
        result = RegisterWorkerResultSuccess(worker_engine_id="eng-1", result_details="ok")

        assert result.worker_engine_id == "eng-1"

    def test_result_failure_can_be_created(self) -> None:
        result = RegisterWorkerResultFailure(result_details="fail")

        assert result is not None


class TestWorkerHeartbeatEvents:
    def test_request_stores_heartbeat_id(self) -> None:
        request = WorkerHeartbeatRequest(heartbeat_id="hb-abc")

        assert request.heartbeat_id == "hb-abc"

    def test_request_is_skip_the_line(self) -> None:
        request = WorkerHeartbeatRequest(heartbeat_id="hb-abc")

        assert isinstance(request, SkipTheLineMixin)

    def test_result_success_stores_heartbeat_id(self) -> None:
        result = WorkerHeartbeatResultSuccess(heartbeat_id="hb-abc", result_details="alive")

        assert result.heartbeat_id == "hb-abc"


class TestUnregisterWorkerEvents:
    def test_request_stores_engine_id(self) -> None:
        request = UnregisterWorkerRequest(worker_engine_id="eng-1")

        assert request.worker_engine_id == "eng-1"

    def test_result_success_stores_engine_id(self) -> None:
        result = UnregisterWorkerResultSuccess(worker_engine_id="eng-1", result_details="ok")

        assert result.worker_engine_id == "eng-1"

    def test_result_failure_can_be_created(self) -> None:
        result = UnregisterWorkerResultFailure(result_details="fail")

        assert result is not None
