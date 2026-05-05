"""Tests for execution event payloads."""

from griptape_nodes.retained_mode.events.base_events import SkipTheLineMixin
from griptape_nodes.retained_mode.events.execution_events import (
    CancelExecuteNodeRequest,
    CancelExecuteNodeResultFailure,
    CancelExecuteNodeResultSuccess,
)


class TestCancelExecuteNodeEvents:
    def test_request_stores_target_request_id(self) -> None:
        request = CancelExecuteNodeRequest(target_request_id="req-123")

        assert request.target_request_id == "req-123"

    def test_request_is_skip_the_line(self) -> None:
        request = CancelExecuteNodeRequest(target_request_id="req-123")

        assert isinstance(request, SkipTheLineMixin)

    def test_request_broadcast_result_defaults_false(self) -> None:
        request = CancelExecuteNodeRequest(target_request_id="req-123")

        assert request.broadcast_result is False

    def test_result_success_can_be_created(self) -> None:
        result = CancelExecuteNodeResultSuccess(result_details="delivered")

        assert result is not None

    def test_result_failure_can_be_created(self) -> None:
        result = CancelExecuteNodeResultFailure(result_details="failed")

        assert result is not None
