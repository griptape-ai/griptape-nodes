from unittest.mock import AsyncMock, Mock, patch

import pytest

from griptape_nodes.retained_mode.events.base_events import ResultPayloadFailure
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from tests.unit.mocks import MockRequest, MockSuccessResult


class TestGriptapeNodesEnqueueResult:
    """Test GriptapeNodes functionality with focus on enqueue_result parameter."""

    def test_handle_request_enqueue_result_true_by_default(self) -> None:
        """Test that handle_request passes enqueue_result=True by default to EventManager."""
        request = MockRequest()
        mock_success_result = MockSuccessResult()

        # Only patch the actual I/O operation - the EventManager.handle_request call
        with patch.object(GriptapeNodes, "EventManager") as mock_event_manager_class:
            mock_event_manager = Mock()
            mock_event_manager.handle_request.return_value = mock_success_result
            mock_event_manager_class.return_value = mock_event_manager

            with patch.object(GriptapeNodes, "WorkflowManager") as mock_workflow_manager_class:
                mock_workflow_manager = Mock()
                mock_workflow_manager_class.return_value = mock_workflow_manager

                result = GriptapeNodes.handle_request(request)

                assert result == mock_success_result
                # Verify that enqueue_result was not explicitly set (defaults to True)
                mock_event_manager.handle_request.assert_called_once()
                call_kwargs = mock_event_manager.handle_request.call_args.kwargs
                assert "enqueue_result" not in call_kwargs or call_kwargs["enqueue_result"] is True

    def test_handle_request_enqueue_result_false(self) -> None:
        """Test that handle_request passes enqueue_result=False to EventManager."""
        request = MockRequest()
        mock_success_result = MockSuccessResult()

        # Only patch the actual I/O operation - the EventManager.handle_request call
        with patch.object(GriptapeNodes, "EventManager") as mock_event_manager_class:
            mock_event_manager = Mock()
            mock_event_manager.handle_request.return_value = mock_success_result
            mock_event_manager_class.return_value = mock_event_manager

            with patch.object(GriptapeNodes, "WorkflowManager") as mock_workflow_manager_class:
                mock_workflow_manager = Mock()
                mock_workflow_manager_class.return_value = mock_workflow_manager

                result = GriptapeNodes.handle_request(request, enqueue_result=False)

                assert result == mock_success_result
                # Verify that enqueue_result=False was passed
                mock_event_manager.handle_request.assert_called_once()
                call_kwargs = mock_event_manager.handle_request.call_args.kwargs
                assert call_kwargs["enqueue_result"] is False

    @pytest.mark.asyncio
    async def test_ahandle_request_enqueue_result_true_by_default(self) -> None:
        """Test that ahandle_request passes enqueue_result=True by default to EventManager."""
        request = MockRequest()
        mock_success_result = MockSuccessResult()

        # Only patch the actual I/O operation - the EventManager.ahandle_request call
        with patch.object(GriptapeNodes, "EventManager") as mock_event_manager_class:
            mock_event_manager = Mock()
            mock_event_manager.ahandle_request = AsyncMock(return_value=mock_success_result)
            mock_event_manager_class.return_value = mock_event_manager

            with patch.object(GriptapeNodes, "WorkflowManager") as mock_workflow_manager_class:
                mock_workflow_manager = Mock()
                mock_workflow_manager_class.return_value = mock_workflow_manager

                result = await GriptapeNodes.ahandle_request(request)

                assert result == mock_success_result
                # Verify that enqueue_result was not explicitly set (defaults to True)
                mock_event_manager.ahandle_request.assert_called_once()
                call_kwargs = mock_event_manager.ahandle_request.call_args.kwargs
                assert "enqueue_result" not in call_kwargs or call_kwargs["enqueue_result"] is True

    @pytest.mark.asyncio
    async def test_ahandle_request_enqueue_result_false(self) -> None:
        """Test that ahandle_request passes enqueue_result=False to EventManager."""
        request = MockRequest()
        mock_success_result = MockSuccessResult()

        # Only patch the actual I/O operation - the EventManager.ahandle_request call
        with patch.object(GriptapeNodes, "EventManager") as mock_event_manager_class:
            mock_event_manager = Mock()
            mock_event_manager.ahandle_request = AsyncMock(return_value=mock_success_result)
            mock_event_manager_class.return_value = mock_event_manager

            with patch.object(GriptapeNodes, "WorkflowManager") as mock_workflow_manager_class:
                mock_workflow_manager = Mock()
                mock_workflow_manager_class.return_value = mock_workflow_manager

                result = await GriptapeNodes.ahandle_request(request, enqueue_result=False)

                assert result == mock_success_result
                # Verify that enqueue_result=False was passed
                mock_event_manager.ahandle_request.assert_called_once()
                call_kwargs = mock_event_manager.ahandle_request.call_args.kwargs
                assert call_kwargs["enqueue_result"] is False

    def test_handle_request_with_response_topic_and_request_id(self) -> None:
        """Test that handle_request passes response_topic and request_id correctly."""
        request = MockRequest()
        mock_success_result = MockSuccessResult()
        response_topic = "custom_topic"
        request_id = "custom_request_id"

        # Only patch the actual I/O operation - the EventManager.handle_request call
        with patch.object(GriptapeNodes, "EventManager") as mock_event_manager_class:
            mock_event_manager = Mock()
            mock_event_manager.handle_request.return_value = mock_success_result
            mock_event_manager_class.return_value = mock_event_manager

            with patch.object(GriptapeNodes, "WorkflowManager") as mock_workflow_manager_class:
                mock_workflow_manager = Mock()
                mock_workflow_manager_class.return_value = mock_workflow_manager

                result = GriptapeNodes.handle_request(
                    request, response_topic=response_topic, request_id=request_id, enqueue_result=False
                )

                assert result == mock_success_result
                # Verify the parameters were passed correctly
                mock_event_manager.handle_request.assert_called_once()
                call_kwargs = mock_event_manager.handle_request.call_args.kwargs
                assert call_kwargs["response_topic"] == response_topic
                assert call_kwargs["request_id"] == request_id
                assert call_kwargs["enqueue_result"] is False

    def test_handle_request_exception_handling(self) -> None:
        """Test that handle_request properly handles exceptions."""
        request = MockRequest()

        # Only patch the actual I/O operation - the EventManager.handle_request call
        with patch.object(GriptapeNodes, "EventManager") as mock_event_manager_class:
            mock_event_manager = Mock()
            mock_event_manager.handle_request.side_effect = ValueError("Test error")
            mock_event_manager_class.return_value = mock_event_manager

            with patch.object(GriptapeNodes, "WorkflowManager") as mock_workflow_manager_class:
                mock_workflow_manager = Mock()
                mock_workflow_manager_class.return_value = mock_workflow_manager

                result = GriptapeNodes.handle_request(request)

                # Should return a failure result
                assert isinstance(result, ResultPayloadFailure)
                assert result.succeeded() is False
