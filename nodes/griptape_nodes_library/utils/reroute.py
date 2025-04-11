from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, DataNode


class Reroute(DataNode):
    # Track the incoming and outgoing connections to choose our allowed types.
    # I'd use sets for faster removal but I don't know if I want to hash Parameter objects
    incoming_connection_params: list[Parameter]
    outgoing_connection_params: list[Parameter]
    passthru: Parameter

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.incoming_connection_params = []
        self.outgoing_connection_params = []

        self.passthru = Parameter(
            name="passThru",
            input_types=["Any"],
            output_type="Any",
            default_value=None,
            tooltip="",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
        )
        self.add_parameter(self.passthru)

    def _is_currently_handling_control_parameters(self) -> bool:
        """Reports if we're already handling a Control parameter."""
        if self.passthru.output_type.lower() == ParameterTypeBuiltin.CONTROL_TYPE.value:
            return True
        for input_type in self.passthru.input_types:
            if input_type.lower() == ParameterTypeBuiltin.CONTROL_TYPE.value:
                return True
        return False

    def _reset_to_single_type(self, type_str: str) -> None:
        self.passthru.input_types = [type_str]
        self.passthru.output_type = type_str

    def after_incoming_connection(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        # Add the connection.
        self.incoming_connection_params.append(source_parameter)
        self._update_types_for_situation()

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        # Stop tracking it.
        self.incoming_connection_params.remove(source_parameter)
        self._update_types_for_situation()

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection has been established OUT of this Node."""
        self.outgoing_connection_params.append(target_parameter)
        self._update_types_for_situation()

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection OUT of this Node was REMOVED."""
        self.outgoing_connection_params.remove(target_parameter)
        self._update_types_for_situation()

    def _update_types_for_situation(self) -> None:
        # If we have any incoming connections, our outgoing will have to match.
        for incoming_connection_param in self.incoming_connection_params:
            if incoming_connection_param.output_type.lower() != ParameterTypeBuiltin.ANY.value:
                self.passthru.input_types = [incoming_connection_param.output_type]
                self.passthru.output_type = incoming_connection_param.output_type
                return

        # If we got here, we had no incoming connections. Yet.
        if self.outgoing_connection_params:
            # We have outgoing ones, so start there.
            possible_inputs = set()
            # Fill up the set with our first one, then we'll intersect.
            first_outgoing_param = self.outgoing_connection_params[0]
            for first_outgoing_param_input_type in first_outgoing_param.input_types:
                input_type_lower = first_outgoing_param_input_type.lower()
                if input_type_lower != ParameterTypeBuiltin.ANY.value:
                    possible_inputs.add(input_type_lower)

            # Now intersect against the remainder.
            for outgoing_param in self.outgoing_connection_params[1:]:
                outgoing_param_input_set = {item.lower() for item in outgoing_param.input_types}
                if ParameterTypeBuiltin.ANY.value in outgoing_param_input_set:
                    # Skip it, since it'll take ANYBODY.
                    continue
                # Intersect with our running set
                possible_inputs = possible_inputs.intersection(outgoing_param_input_set)

            if len(possible_inputs) > 0:
                # Use this intersection for our inputs allowed.
                self.passthru.input_types = list(possible_inputs)
                return

        # If we got all the way down here, we don't have enough information or everyone is Any.
        self.passthru.output_type = ParameterTypeBuiltin.ANY.value
        self.passthru.input_types = [ParameterTypeBuiltin.ANY.value]

    def process(self) -> None:
        pass
