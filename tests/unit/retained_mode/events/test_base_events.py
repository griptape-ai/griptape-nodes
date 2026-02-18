"""Tests for RequestPayload base class broadcast_result behavior."""

from griptape_nodes.retained_mode.events.base_events import RequestPayload
from griptape_nodes.retained_mode.events.os_events import ReadFileRequest


class TestBroadcastResultDefaults:
    def test_request_payload_broadcasts_by_default(self) -> None:
        """All RequestPayload subclasses broadcast results unless they opt out."""
        assert RequestPayload.broadcast_result is True

    def test_read_file_request_does_not_broadcast_by_default(self) -> None:
        """ReadFileRequest opts out of broadcasting to avoid sending large payloads."""
        assert ReadFileRequest.broadcast_result is False

    def test_broadcast_result_false_accessible_on_instance(self) -> None:
        """broadcast_result is accessible on instances as well as the class."""
        request = ReadFileRequest()
        assert request.broadcast_result is False
