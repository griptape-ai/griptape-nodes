from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode


class OutputSelector(ControlNode):
    ignore_dependencies: bool = True

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.my_list = ParameterList(
            name="select_inputs",
            tooltip="Select one of these outputs",
            input_types=["Any"],
            allowed_modes={ParameterMode.INPUT},
        )
        self.add_parameter(self.my_list)
        self.output_param = Parameter(
            name="output",
            tooltip="Output that has been selected",
            output_type=ParameterTypeBuiltin.ALL.value,
            default_value=None,
            allowed_modes={ParameterMode.OUTPUT},
        )
        self.add_parameter(self.output_param)

    def process(self) -> None:
        # Go through to get the output.
        for child in self.my_list.find_elements_by_type(Parameter, find_recursively=False):
            value = self.get_parameter_value(child.name)
            if value is not None:
                self.parameter_output_values["output"] = value
                self.remove_parameter_value(child.name)

    def after_incoming_connection(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        # Add the connection.
        if (
            target_parameter != self.get_parameter_by_name("exec_in")
            and self.output_param.output_type == ParameterTypeBuiltin.ALL.value
        ):
            self.output_param.output_type = source_parameter.output_type

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        # Stop tracking it.
        if target_parameter != self.get_parameter_by_name("exec_in"):
            self.output_param.output_type = ParameterTypeBuiltin.ALL.value
            # We just want to get rid of it if it exists. If it doesn't exist, that's fine.
            if "output" in self.parameter_values:
                self.remove_parameter_value("output")

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection has been established OUT of this Node."""
        if source_parameter != self.get_parameter_by_name("exec_out"):
            self.my_list.input_types = target_parameter.input_types

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Callback after a Connection OUT of this Node was REMOVED."""
        if source_parameter != self.get_parameter_by_name("exec_out"):
            self.my_list.input_types = ["Any"]

    # Overloading the BaseNode method. Normally, initialize spotlight creates a linked list of Parameters to traverse down
    # when evaluating dependencies. However, we don't want this node to traverse backwards if it's receiving one output
    # from one of two flows (since this would start both connected sets of nodes.) So we return None.
    def initialize_spotlight(self) -> None:
        return None
