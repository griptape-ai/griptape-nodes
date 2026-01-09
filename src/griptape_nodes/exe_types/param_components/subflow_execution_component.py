from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode


class SubflowExecutionComponent:
    """A reusable component for managing subprocess execution event parameters.

    This component creates and manages an "execution_events" parameter that displays
    real-time events from subprocess execution in the GUI.
    """

    def __init__(self, node: BaseNode) -> None:
        """Initialize the SubflowExecutionComponent.

        Args:
            node: The node instance that will own the parameter
        """
        self._node = node

    def add_output_parameters(self) -> None:
        """Add the execution_events output parameter to the node."""
        self._node.add_parameter(
            Parameter(
                name="execution_events",
                output_type="str",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Real-time events from subprocess execution",
                ui_options={"multiline": True},
            )
        )
        if "execution_panel" not in self._node.metadata:
            self._node.metadata["execution_panel"] = {"params": []}
        self._node.metadata["execution_panel"]["params"].append("execution_events")

    def clear_events(self) -> None:
        """Clear events at start of execution."""
        self._node.publish_update_to_parameter("execution_events", "")

    def append_event(self, event_str: str) -> None:
        """Append a stringified event to the parameter.

        Args:
            event_str: The event string to append
        """
        self._node.append_value_to_parameter("execution_events", event_str + "\n")
