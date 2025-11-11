from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode


class SubFlowNode(ControlNode):
    """Node that executes a subflow or workflow.

    Either flow_name or workflow_name must be provided, but not both.
    """

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Flow/Workflow parameters
        self.flow_name = Parameter(
            name="flow_name",
            tooltip="Name of the flow to execute (optional if workflow_name is provided)",
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value="",
        )
        self.add_parameter(self.flow_name)

        self.workflow_name = Parameter(
            name="workflow_name",
            tooltip="Name of the workflow to execute (optional if flow_name is provided)",
            type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value="",
        )
        self.add_parameter(self.workflow_name)

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate that exactly one of flow_name or workflow_name is provided."""
        exceptions = []

        flow_name_value = self.get_parameter_value("flow_name")
        workflow_name_value = self.get_parameter_value("workflow_name")

        # Check if flow_name is empty or None
        flow_name_empty = not flow_name_value or (isinstance(flow_name_value, str) and not flow_name_value.strip())

        # Check if workflow_name is empty or None
        workflow_name_empty = not workflow_name_value or (isinstance(workflow_name_value, str) and not workflow_name_value.strip())

        # Both cannot be empty - at least one must be provided
        if flow_name_empty and workflow_name_empty:
            msg = f"{self.name}: Either flow_name or workflow_name must be provided"
            exceptions.append(Exception(msg))

        # Both cannot be provided - only one can be filled
        if not flow_name_empty and not workflow_name_empty:
            msg = f"{self.name}: Only one of flow_name or workflow_name can be provided, not both"
            exceptions.append(Exception(msg))

        # Call parent validation
        parent_exceptions = super().validate_before_node_run()
        if parent_exceptions:
            exceptions.extend(parent_exceptions)

        return exceptions if exceptions else None

    async def aprocess(self) -> None:
        """Process the subflow execution.

        Implementation to be added.
        """
        from griptape_nodes.retained_mode
        file_name = self.get_parameter_value("workflow_name")
        if file_name is not None:



