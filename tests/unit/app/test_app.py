from unittest.mock import AsyncMock, Mock, patch

import pytest

from griptape_nodes.app.app import _process_api_event
from griptape_nodes.retained_mode.events.base_events import EventRequest
from tests.unit.mocks import MockFailureResult, MockRequest, MockSkipTheLineRequest, MockSuccessResult


class TestProcessApiEvent:
    """Test _process_api_event functionality with focus on SkipTheLineMixin behavior."""

    @pytest.mark.asyncio
    async def test_process_api_event_skip_the_line_success(self) -> None:
        """Test _process_api_event with SkipTheLineMixin request that succeeds."""
        skip_request = MockSkipTheLineRequest(request_id=123)
        success_result = MockSuccessResult()

        event_data = {
            "payload": {
                "event_type": "EventRequest",
                "request": {"request_type": "MockSkipTheLineRequest", "request_id": 123},
                "response_topic": "test_topic",
                "request_id": "test_request_id",
            }
        }

        # Only patch the I/O operations: griptape_nodes.ahandle_request and __emit_message
        with patch("griptape_nodes.app.app.griptape_nodes") as mock_griptape_nodes:
            mock_griptape_nodes.ahandle_request = AsyncMock(return_value=success_result)

            # Mock the deserialize_event function (this is effectively I/O since it parses external data)
            with patch("griptape_nodes.app.app.deserialize_event") as mock_deserialize:
                mock_event_request = EventRequest(
                    request=skip_request, response_topic="test_topic", request_id="test_request_id"
                )
                mock_deserialize.return_value = mock_event_request

                # Mock the __emit_message function (this is I/O - sending messages)
                with patch("griptape_nodes.app.app.__emit_message") as mock_emit:
                    await _process_api_event(event_data)

                    # Verify that ahandle_request was called with enqueue_result=False
                    mock_griptape_nodes.ahandle_request.assert_called_once_with(
                        skip_request, response_topic="test_topic", request_id="test_request_id", enqueue_result=False
                    )

                    # Verify that success result was emitted
                    mock_emit.assert_called_once()
                    emit_args = mock_emit.call_args
                    assert emit_args[0][0] == "success_result"  # dest_socket
                    assert "test_topic" in emit_args.kwargs.values()  # topic

    @pytest.mark.asyncio
    async def test_process_api_event_skip_the_line_failure(self) -> None:
        """Test _process_api_event with SkipTheLineMixin request that fails."""
        skip_request = MockSkipTheLineRequest(request_id=123)
        failure_result = MockFailureResult()

        event_data = {
            "payload": {
                "event_type": "EventRequest",
                "request": {"request_type": "MockSkipTheLineRequest", "request_id": 123},
                "response_topic": "test_topic",
                "request_id": "test_request_id",
            }
        }

        # Only patch the I/O operations: griptape_nodes.ahandle_request and __emit_message
        with patch("griptape_nodes.app.app.griptape_nodes") as mock_griptape_nodes:
            mock_griptape_nodes.ahandle_request = AsyncMock(return_value=failure_result)

            # Mock the deserialize_event function (this is effectively I/O since it parses external data)
            with patch("griptape_nodes.app.app.deserialize_event") as mock_deserialize:
                mock_event_request = EventRequest(
                    request=skip_request, response_topic="test_topic", request_id="test_request_id"
                )
                mock_deserialize.return_value = mock_event_request

                # Mock the __emit_message function (this is I/O - sending messages)
                with patch("griptape_nodes.app.app.__emit_message") as mock_emit:
                    await _process_api_event(event_data)

                    # Verify that ahandle_request was called with enqueue_result=False
                    mock_griptape_nodes.ahandle_request.assert_called_once_with(
                        skip_request, response_topic="test_topic", request_id="test_request_id", enqueue_result=False
                    )

                    # Verify that failure result was emitted
                    mock_emit.assert_called_once()
                    emit_args = mock_emit.call_args
                    assert emit_args[0][0] == "failure_result"  # dest_socket
                    assert "test_topic" in emit_args.kwargs.values()  # topic

    @pytest.mark.asyncio
    async def test_process_api_event_regular_request(self) -> None:
        """Test _process_api_event with regular (non-SkipTheLine) request."""
        regular_request = MockRequest(request_id=123)

        event_data = {
            "payload": {
                "event_type": "EventRequest",
                "request": {"request_type": "MockRequest", "request_id": 123},
                "response_topic": "test_topic",
                "request_id": "test_request_id",
            }
        }

        # Only patch the I/O operations: EventManager.aput_event
        with patch("griptape_nodes.app.app.griptape_nodes") as mock_griptape_nodes:
            mock_event_manager = Mock()
            mock_event_manager.aput_event = AsyncMock()
            mock_griptape_nodes.EventManager.return_value = mock_event_manager

            # Mock the deserialize_event function (this is effectively I/O since it parses external data)
            with patch("griptape_nodes.app.app.deserialize_event") as mock_deserialize:
                mock_event_request = EventRequest(
                    request=regular_request, response_topic="test_topic", request_id="test_request_id"
                )
                mock_deserialize.return_value = mock_event_request

                await _process_api_event(event_data)

                # Verify that the event was added to the queue instead of being processed immediately
                mock_event_manager.aput_event.assert_called_once_with(mock_event_request)

                # Verify that ahandle_request was NOT called directly
                mock_griptape_nodes.ahandle_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_api_event_invalid_event_type(self) -> None:
        """Test _process_api_event handles non-EventRequest event types properly."""
        event_data = {
            "payload": {"event_type": "SomeOtherEvent", "request": {"some_field": "value"}, "data": "test_data"}
        }

        # This should raise a RuntimeError because event_type is not "EventRequest"
        # No mocking needed - this tests the validation logic directly
        with pytest.raises(RuntimeError, match="did not match 'EventRequest'"):
            await _process_api_event(event_data)

    @pytest.mark.asyncio
    async def test_process_api_event_missing_request_field(self) -> None:
        """Test _process_api_event handles missing request field properly."""
        event_data = {"payload": {"event_type": "EventRequest", "data": "test_data"}}

        # This should raise a RuntimeError because 'request' field is missing
        # No mocking needed - this tests the validation logic directly
        with pytest.raises(RuntimeError, match="'request' was expected but not found"):
            await _process_api_event(event_data)
