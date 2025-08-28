"""Common mock objects for testing."""

from unittest.mock import Mock

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    SkipTheLineMixin,
)


class MockRequest(RequestPayload):
    """Mock request for testing."""

    def __init__(self, request_id: int | None = None):
        self.request_id = request_id


class MockSkipTheLineRequest(RequestPayload, SkipTheLineMixin):
    """Mock SkipTheLine request for testing."""

    def __init__(self, request_id: int | None = None):
        self.request_id = request_id


class MockSuccessResult(ResultPayloadSuccess):
    """Mock success result for testing."""

    def __init__(self, result_details: str = "Success"):
        super().__init__(result_details=result_details)


class MockFailureResult(ResultPayloadFailure):
    """Mock failure result for testing."""

    def __init__(self, result_details: str = "Failure"):
        super().__init__(result_details=result_details)


def create_mock_workflow_manager() -> Mock:
    """Create a properly configured mock WorkflowManager."""
    mock_mgr = Mock()
    mock_mgr.should_squelch_workflow_altered.return_value = False
    return mock_mgr


def create_mock_operation_depth_manager() -> Mock:
    """Create a properly configured mock OperationDepthManager."""
    mock_mgr = Mock()
    mock_mgr.__enter__ = Mock(return_value=mock_mgr)
    mock_mgr.__exit__ = Mock(return_value=None)
    mock_mgr.is_top_level.return_value = False
    mock_mgr.request_retained_mode_translation.return_value = None
    return mock_mgr
