"""Unit tests for WorkflowExecutor class."""

from typing import Any
from unittest.mock import AsyncMock

import pytest  # type: ignore[reportMissingImports]

from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.drivers.storage import StorageBackend


class ConcreteWorkflowExecutor(WorkflowExecutor):
    """Concrete implementation of WorkflowExecutor for testing."""

    def __init__(self) -> None:
        super().__init__()
        self.arun_mock = AsyncMock()

    async def arun(
        self,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
        **kwargs: Any,
    ) -> None:
        await self.arun_mock(flow_input, storage_backend, **kwargs)


class TestWorkflowExecutor:
    """Test suite for WorkflowExecutor class."""

    def test_init(self) -> None:
        """Test WorkflowExecutor initialization."""
        executor = ConcreteWorkflowExecutor()
        assert executor.output is None

    def test_init_sets_output_to_none(self) -> None:
        """Test that initialization sets output to None."""
        executor = ConcreteWorkflowExecutor()
        executor.output = {"test": "data"}

        # Create a new executor
        new_executor = ConcreteWorkflowExecutor()
        assert new_executor.output is None

    @pytest.mark.asyncio
    async def test_arun_is_abstract(self) -> None:
        """Test that arun method is properly defined in concrete implementation."""
        executor = ConcreteWorkflowExecutor()

        # Test that arun can be called with required parameters
        await executor.arun({"input": "data"})

        # Verify the mock was called with correct arguments
        executor.arun_mock.assert_called_once_with({"input": "data"}, StorageBackend.LOCAL)

    @pytest.mark.asyncio
    async def test_arun_with_custom_storage_backend(self) -> None:
        """Test arun method with custom storage backend."""
        executor = ConcreteWorkflowExecutor()

        await executor.arun({"input": "data"}, StorageBackend.GTC)

        executor.arun_mock.assert_called_once_with({"input": "data"}, StorageBackend.GTC)

    @pytest.mark.asyncio
    async def test_arun_with_kwargs(self) -> None:
        """Test arun method with additional keyword arguments."""
        executor = ConcreteWorkflowExecutor()

        await executor.arun({"input": "data"}, StorageBackend.LOCAL, extra_param="test_value", another_param=42)

        executor.arun_mock.assert_called_once_with(
            {"input": "data"}, StorageBackend.LOCAL, extra_param="test_value", another_param=42
        )

    def test_run_calls_arun_with_correct_parameters(self) -> None:
        """Test that run method calls arun with correct parameters."""
        executor = ConcreteWorkflowExecutor()

        # Call the synchronous run method
        executor.run({"input": "data"})

        # Verify arun was called with correct parameters
        executor.arun_mock.assert_called_once_with({"input": "data"}, StorageBackend.LOCAL)

    def test_run_with_custom_storage_backend(self) -> None:
        """Test run method with custom storage backend."""
        executor = ConcreteWorkflowExecutor()

        executor.run({"input": "data"}, StorageBackend.GTC)

        # Verify arun was called with correct storage backend
        executor.arun_mock.assert_called_once_with({"input": "data"}, StorageBackend.GTC)

    def test_run_with_kwargs(self) -> None:
        """Test run method with additional keyword arguments."""
        executor = ConcreteWorkflowExecutor()

        executor.run({"input": "data"}, StorageBackend.LOCAL, extra_param="test_value")

        # Verify arun was called with correct parameters including kwargs
        executor.arun_mock.assert_called_once_with({"input": "data"}, StorageBackend.LOCAL, extra_param="test_value")

    def test_run_returns_none(self) -> None:
        """Test that run method returns None."""
        executor = ConcreteWorkflowExecutor()

        # Just call run() directly - arun_mock is already an AsyncMock that returns None
        result = executor.run({"input": "data"})

        assert result is None
        executor.arun_mock.assert_called_once_with({"input": "data"}, StorageBackend.LOCAL)

    def test_output_property_can_be_set(self) -> None:
        """Test that output property can be set and retrieved."""
        executor = ConcreteWorkflowExecutor()

        test_output = {"result": "success", "data": [1, 2, 3]}
        executor.output = test_output

        assert executor.output == test_output

    def test_output_property_can_be_none(self) -> None:
        """Test that output property can be set to None."""
        executor = ConcreteWorkflowExecutor()
        executor.output = {"some": "data"}

        executor.output = None
        assert executor.output is None

    def test_abstract_method_enforcement(self) -> None:
        """Test that WorkflowExecutor cannot be instantiated directly due to abstract method."""
        # This test verifies that the arun method is properly marked as abstract
        # We can't instantiate WorkflowExecutor directly, but we can verify the abstract method exists
        assert hasattr(WorkflowExecutor, "arun")
        assert getattr(WorkflowExecutor.arun, "__isabstractmethod__", False)


class TestWorkflowExecutorIntegration:
    """Integration tests for WorkflowExecutor functionality."""

    @pytest.mark.asyncio
    async def test_full_workflow_execution_cycle(self) -> None:
        """Test a complete workflow execution cycle."""
        executor = ConcreteWorkflowExecutor()

        # Set up the mock to simulate setting output
        async def mock_arun(*_args: Any, **_kwargs: Any) -> None:
            executor.output = {"workflow_result": "completed"}

        executor.arun_mock.side_effect = mock_arun

        # Execute the workflow
        await executor.arun({"test_input": "value"})

        # Verify the workflow was called and output was set
        executor.arun_mock.assert_called_once()
        assert executor.output == {"workflow_result": "completed"}

    def test_synchronous_wrapper_integration(self) -> None:
        """Test the synchronous run method integration."""
        executor = ConcreteWorkflowExecutor()

        # Set up the mock to simulate setting output
        async def mock_arun(*_args: Any, **_kwargs: Any) -> None:
            executor.output = {"sync_result": "success"}

        executor.arun_mock.side_effect = mock_arun

        # Execute synchronously
        result = executor.run({"input": "data"})

        # Verify execution completed
        assert result is None  # run method returns None
        assert executor.output == {"sync_result": "success"}
