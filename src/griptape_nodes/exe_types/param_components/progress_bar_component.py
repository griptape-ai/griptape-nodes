import logging

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger(__name__)


class ProgressBarComponent:
    def __init__(self, node: BaseNode):
        self._node = node
        self._total_steps = 0
        self._current_step = 0

    def add_property_parameters(self) -> None:
        self._node.add_parameter(
            Parameter(
                name="progress",
                output_type="float",
                allowed_modes={ParameterMode.PROPERTY},
                tooltip="Progress bar showing completion (0.0 to 1.0)",
                ui_options={"progress_bar": True},
                settable=False,
            )
        )

    def initialize(self, total_steps: int) -> None:
        """Initialize the progress bar with a total number of steps."""
        self._total_steps = total_steps
        self._current_step = 0
        self._update_progress()

    def increment(self, steps: int = 1) -> None:
        """Increment the progress by the specified number of steps."""
        self._current_step += steps
        if self._current_step > self._total_steps:
            logger.warning(
                "Current step %i exceeds total steps %i. Progress will not exceed 100%.",
                self._current_step,
                self._total_steps,
            )
        self._update_progress()

    def reset(self) -> None:
        """Reset the progress bar to 0."""
        self._current_step = 0
        self._total_steps = 0
        self._update_progress()

    def _update_progress(self) -> None:
        """Update the progress parameter based on current step and total steps."""
        if self._total_steps <= 0:
            progress_value = 0.0
        else:
            progress_value = min(1.0, self._current_step / self._total_steps)

        self._node.publish_update_to_parameter("progress", progress_value)
