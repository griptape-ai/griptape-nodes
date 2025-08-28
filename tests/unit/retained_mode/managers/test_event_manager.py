from unittest.mock import AsyncMock, Mock, patch

import pytest

from griptape_nodes.retained_mode.managers.event_manager import EventManager
from tests.unit.mocks import (
    MockFailureResult,
    MockRequest,
    MockSuccessResult,
    create_mock_operation_depth_manager,
    create_mock_workflow_manager,
)


class TestEventManagerEnqueueResult:
    """Test EventManager functionality with focus on enqueue_result parameter."""

    @pytest.fixture
    def event_manager(self) -> EventManager:
        """Create a fresh EventManager instance for testing."""
        return EventManager()

    @pytest.fixture
    def mock_workflow_manager(self) -> Mock:
        """Create a mock WorkflowManager."""
        return create_mock_workflow_manager()

    @pytest.fixture
    def mock_operation_depth_manager(self) -> Mock:
        """Create a mock OperationDepthManager."""
        return create_mock_operation_depth_manager()

    @pytest.mark.parametrize(
        ("enqueue_result", "expected_calls"),
        [
            (True, 1),  # Default behavior - should enqueue
            (False, 0),  # Explicit False - should not enqueue
        ],
    )
    def test_handle_request_enqueue_result_behavior(
        self,
        event_manager: EventManager,
        mock_workflow_manager: Mock,
        mock_operation_depth_manager: Mock,
        enqueue_result: bool,  # noqa: FBT001
        expected_calls: int,
    ) -> None:
        """Test that handle_request respects enqueue_result parameter."""
        request = MockRequest()
        mock_success_result = MockSuccessResult()

        # Mock the handler to return success
        mock_handler = Mock(return_value=mock_success_result)
        event_manager._request_type_to_manager[MockRequest] = mock_handler

        # Only patch the I/O operation (putting events in queue)
        with patch.object(event_manager, "put_event") as mock_put_event:
            kwargs = {
                "operation_depth_mgr": mock_operation_depth_manager,
                "workflow_mgr": mock_workflow_manager,
                "enqueue_result": enqueue_result,
            }

            result = event_manager.handle_request(request, **kwargs)

            assert result == mock_success_result
            assert mock_put_event.call_count == expected_calls

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("enqueue_result", "expected_calls"),
        [
            (True, 1),  # Default behavior - should enqueue
            (False, 0),  # Explicit False - should not enqueue
        ],
    )
    async def test_ahandle_request_enqueue_result_behavior(
        self,
        event_manager: EventManager,
        mock_workflow_manager: Mock,
        mock_operation_depth_manager: Mock,
        enqueue_result: bool,  # noqa: FBT001
        expected_calls: int,
    ) -> None:
        """Test that ahandle_request respects enqueue_result parameter."""
        request = MockRequest()
        mock_success_result = MockSuccessResult()

        # Mock the handler to return success (async)
        mock_handler = AsyncMock(return_value=mock_success_result)
        event_manager._request_type_to_manager[MockRequest] = mock_handler

        # Only patch the I/O operation (putting events in queue)
        with patch.object(event_manager, "put_event") as mock_put_event:
            kwargs = {
                "operation_depth_mgr": mock_operation_depth_manager,
                "workflow_mgr": mock_workflow_manager,
                "enqueue_result": enqueue_result,
            }

            result = await event_manager.ahandle_request(request, **kwargs)

            assert result == mock_success_result
            assert mock_put_event.call_count == expected_calls

    @pytest.mark.parametrize(
        ("result_type", "enqueue_result", "expected_calls"),
        [
            (MockSuccessResult, True, 1),
            (MockSuccessResult, False, 0),
            (MockFailureResult, True, 1),
            (MockFailureResult, False, 0),
        ],
    )
    def test_handle_request_with_different_result_types(  # noqa: PLR0913
        self,
        event_manager: EventManager,
        mock_workflow_manager: Mock,
        mock_operation_depth_manager: Mock,
        result_type: type,
        enqueue_result: bool,  # noqa: FBT001
        expected_calls: int,
    ) -> None:
        """Test that handle_request respects enqueue_result parameter with both success and failure results."""
        request = MockRequest()
        mock_result = result_type()

        # Mock the handler to return the specified result type
        mock_handler = Mock(return_value=mock_result)
        event_manager._request_type_to_manager[MockRequest] = mock_handler

        # Only patch the I/O operation (putting events in queue)
        with patch.object(event_manager, "put_event") as mock_put_event:
            kwargs = {
                "operation_depth_mgr": mock_operation_depth_manager,
                "workflow_mgr": mock_workflow_manager,
                "enqueue_result": enqueue_result,
            }

            result = event_manager.handle_request(request, **kwargs)

            assert result == mock_result
            assert mock_put_event.call_count == expected_calls

    def test_handle_request_with_response_topic_and_request_id(
        self, event_manager: EventManager, mock_workflow_manager: Mock, mock_operation_depth_manager: Mock
    ) -> None:
        """Test that handle_request passes response_topic and request_id correctly."""
        request = MockRequest()
        mock_success_result = MockSuccessResult()
        response_topic = "custom_topic"
        request_id = "custom_request_id"

        # Mock the handler to return success
        mock_handler = Mock(return_value=mock_success_result)
        event_manager._request_type_to_manager[MockRequest] = mock_handler

        # Only patch the I/O operation (putting events in queue)
        with patch.object(event_manager, "put_event") as mock_put_event:
            result = event_manager.handle_request(
                request,
                operation_depth_mgr=mock_operation_depth_manager,
                workflow_mgr=mock_workflow_manager,
                response_topic=response_topic,
                request_id=request_id,
            )

            assert result == mock_success_result
            # Verify the event was enqueued with correct topic and request_id
            mock_put_event.assert_called_once()
            call_args = mock_put_event.call_args[0][0]
            assert hasattr(call_args, "wrapped_event")
