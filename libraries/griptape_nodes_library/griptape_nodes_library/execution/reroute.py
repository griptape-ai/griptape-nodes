from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, DataNode


class Reroute(DataNode):
    # Track the incoming and outgoing connections to choose our allowed types.
    # I'd use sets for faster removal but I don't know if I want to hash Parameter objects
    passthru: Parameter

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.passthru = Parameter(
            name="passThru",
            input_types=["Any"],
            output_type=ParameterTypeBuiltin.ALL.value,
            default_value=None,
            tooltip="",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
        )
        self.add_parameter(self.passthru)

    def after_incoming_connection(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,
        target_parameter: Parameter,  # noqa: ARG002
        modified_parameters_set: set[str],  # noqa: ARG002
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        # Add the connection.
        self.passthru.output_type = source_parameter.output_type

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
        modified_parameters_set: set[str],  # noqa: ARG002
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        # Stop tracking it.
        self.passthru.output_type = ParameterTypeBuiltin.ALL.value
        # We just want to get rid of it if it exists. If it doesn't exist, that's fine.
        if "passThru" in self.parameter_values:
            self.remove_parameter_value("passThru")

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,
        modified_parameters_set: set[str],  # noqa: ARG002
    ) -> None:
        """Callback after a Connection has been established OUT of this Node."""
        self.passthru.input_types = target_parameter.input_types

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
        modified_parameters_set: set[str],  # noqa: ARG002
    ) -> None:
        """Callback after a Connection OUT of this Node was REMOVED."""
        self.passthru.input_types = ["Any"]

    def process(self) -> None:
        pass
