"""Base class for retry node groups."""

from __future__ import annotations

from abc import abstractmethod
from enum import StrEnum
from typing import Any

from griptape_nodes.exe_types.core_types import (
    ControlParameterInput,
    Parameter,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.node_groups.subflow_node_group import SubflowNodeGroup

DEFAULT_MAX_RETRIES = 3


class RetryControlParam(StrEnum):
    """Parameter names for retry control on retry node groups."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BaseRetryNodeGroup(SubflowNodeGroup):
    """Base class for retry node groups.

    A group that executes its child nodes and can re-execute them if a failure
    signal is received, up to a configurable maximum number of retries.

    Child nodes connect their success/failure control outputs to the group's
    'succeeded' and 'failed' control input parameters on the right side.
    When 'failed' is triggered and retries remain, the group re-executes.
    When 'succeeded' is triggered or retries are exhausted, execution completes.

    Subclasses must implement:
        - _on_retry(attempt: int): Called before each retry attempt
    """

    # Retry state
    _current_attempt: int
    _max_retries_value: int

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Initialize retry state
        self._current_attempt = 0
        self._max_retries_value = DEFAULT_MAX_RETRIES

        # Max retries parameter (property, shown in group settings)
        self.max_retries = Parameter(
            name="max_retries",
            tooltip="Maximum number of retry attempts (0 means run once with no retries)",
            type=ParameterTypeBuiltin.INT.value,
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value=DEFAULT_MAX_RETRIES,
        )
        self.add_parameter(self.max_retries)

        # Attempt number output (left side - feeds into group)
        self.attempt_number = Parameter(
            name="attempt_number",
            tooltip="Current attempt number (0-based: 0 is the first attempt, 1 is the first retry, etc.)",
            type=ParameterTypeBuiltin.INT.value,
            allowed_modes={ParameterMode.OUTPUT},
            settable=False,
            default_value=0,
        )
        self.add_parameter(self.attempt_number)

        # Track left parameters for UI layout
        if "left_parameters" not in self.metadata:
            self.metadata["left_parameters"] = []
        self.metadata["left_parameters"].append("attempt_number")

        # Control input for success (right side)
        self.succeeded = ControlParameterInput(
            tooltip="Signal that the group executed successfully - stop retrying",
            name=RetryControlParam.SUCCEEDED.value,
        )
        self.succeeded.ui_options = {"display_name": "Succeeded"}
        self.add_parameter(self.succeeded)

        # Control input for failure (right side)
        self.failed = ControlParameterInput(
            tooltip="Signal that the group execution failed - retry if attempts remain",
            name=RetryControlParam.FAILED.value,
        )
        self.failed.ui_options = {"display_name": "Failed"}
        self.add_parameter(self.failed)

        # Was successful output (right side)
        self.was_successful = Parameter(
            name="was_successful",
            tooltip="Whether the group ultimately succeeded after all attempts",
            type=ParameterTypeBuiltin.BOOL.value,
            allowed_modes={ParameterMode.OUTPUT},
            settable=False,
            default_value=False,
        )
        self.add_parameter(self.was_successful)

        # Track right parameters for UI layout
        if "right_parameters" not in self.metadata:
            self.metadata["right_parameters"] = []
        self.metadata["right_parameters"].extend(
            [
                RetryControlParam.SUCCEEDED.value,
                RetryControlParam.FAILED.value,
                "was_successful",
            ]
        )

    @abstractmethod
    def _on_retry(self, attempt: int) -> None:
        """Called before each retry attempt.

        Subclasses can use this to update UI state, log messages, etc.

        Args:
            attempt: The upcoming attempt number (1-based retry count)
        """

    def _on_complete(self, *, succeeded: bool, attempts: int) -> None:
        """Called after all retry attempts are finished, before the node resolves.

        Subclasses can override this to update UI state, log summaries, clean up resources, etc.

        Args:
            succeeded: Whether the group ultimately succeeded
            attempts: Total number of attempts that were executed
        """

    def _initialize_retry_data(self) -> None:
        """Initialize retry-specific data and state."""
        self._current_attempt = 0
        max_retries = self.get_parameter_value("max_retries")
        self._max_retries_value = max_retries if max_retries is not None else DEFAULT_MAX_RETRIES

    def _get_max_retries(self) -> int:
        """Return the maximum number of retries."""
        return self._max_retries_value

    def reset_for_workflow_run(self) -> None:
        """Reset state for a fresh workflow run."""
        self._current_attempt = 0
        self._max_retries_value = DEFAULT_MAX_RETRIES

    async def aprocess(self) -> None:
        """Execute the retry node group.

        Note: This method is typically not called directly. The NodeExecutor
        detects BaseRetryNodeGroup instances and calls handle_retry_group_execution()
        instead. This implementation exists as a fallback for direct local execution.
        """
        await self.execute_subflow()
