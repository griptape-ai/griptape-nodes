from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterTypeBuiltin
from griptape_nodes.exe_types.node_types import BaseNode, DataNode


def contains_any(types: set[str]) -> bool:
    """Check if set of type strings contains the built in any type.

    Args:
        types: Set of type strings to check.

    Returns:
        True if set contains the built in any type, False otherwise.
    """
    for t in types:
        if t.lower() == ParameterTypeBuiltin.ANY.value:
            return True
    return False


def has_control_type(param: Parameter) -> bool:
    """Check if a parameter has a control type.

    Args:
        param: The parameter to check for control type.

    Returns:
        True if the parameter has a control type, False otherwise.
    """
    return param.type == ParameterTypeBuiltin.CONTROL_TYPE.value


class Reroute(DataNode):
    # Track the incoming and outgoing connections to choose our allowed types.
    # I'd use sets for faster removal but I don't know if I want to hash Parameter objects
    passthru: Parameter

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.pass_thru = Parameter(
            name="passThru",
            input_types=[ParameterTypeBuiltin.ANY.value],
            output_type=ParameterTypeBuiltin.ALL.value,
            default_value=None,
            tooltip="",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            hide_property=True,
        )
        self.add_parameter(self.pass_thru)

        self.incoming_source_parameter: Parameter | None = None
        self.outgoing_target_parameters: dict[str, Parameter] = {}

    def after_incoming_connection(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        if has_control_type(source_parameter) or has_control_type(target_parameter):
            # No custom reroute logic for control parameters.
            return
        self.incoming_source_parameter = source_parameter
        self._propagate_forwards()

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        if has_control_type(source_parameter) or has_control_type(target_parameter):
            # No custom reroute logic for control parameters.
            return
        self.incoming_source_parameter = None
        self._propagate_forwards()

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection has been established OUT of this Node."""
        if has_control_type(source_parameter) or has_control_type(target_parameter):
            # No custom reroute logic for control parameters.
            return
        self._add_outgoing_target_parameter(target_node, target_parameter)
        self._propagate_backwards()

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection OUT of this Node was REMOVED."""
        if has_control_type(source_parameter) or has_control_type(target_parameter):
            # No custom reroute logic for control parameters.
            return
        self._remove_outgoing_target_parameter(target_node, target_parameter)
        self._propagate_backwards()

    def process(self) -> None:
        pass

    def _resolve_types(self) -> None:
        if self.incoming_source_parameter is not None and len(self.outgoing_target_parameters) > 0:
            # Incoming and outgoing connections.
            self._use_outgoing_target_parameters_type_intersection()
            # The type/output_type of the input takes precedence, but the input
            # type comes from the outgoing connections for the case when you
            # directly connect a different incoming edge. In that case it should
            # allow any valid input type that the outgoing targets accept.
            self.pass_thru.type = self.incoming_source_parameter.type
            self.pass_thru.output_type = self.incoming_source_parameter.output_type
        elif self.incoming_source_parameter is not None:
            # Incoming connection only.
            self._use_incoming_source_parameter_types()
        elif len(self.outgoing_target_parameters) > 0:
            # Outgoing connections only.
            self._use_outgoing_target_parameters_type_intersection()
        else:
            # No connections.
            self._reset_parameter_types()

        self._ensure_output_uses_all_instead_of_any()

    def _propagate_backwards(self) -> None:
        # Resolve backward to propagate type changes from outgoing connections.
        self._resolve_types()
        incoming_node = None
        if self.incoming_source_parameter is not None:
            incoming_node = self.incoming_source_parameter.get_node()
        if isinstance(incoming_node, self.__class__):
            # If we haven't reached the root, keep going.
            incoming_node._propagate_backwards()
        else:
            # Reached root, prop forward now.
            # The type/value may have been updated with knowledge of the leaves.
            # If you don't prop forward then you will not be able to reset a serial
            # connected subgraph of only reroute nodes to there initial "Any" state.
            self._propagate_forwards()

    def _propagate_forwards(self) -> None:
        # Resolve forward to propagate type changes from incoming connections.
        self._resolve_types()
        for param in self.outgoing_target_parameters.values():
            node = param.get_node()
            if node and isinstance(node, self.__class__):
                # Outgoing connections also need values to propagate.
                value = self.get_parameter_value(self.pass_thru.name)
                node.set_parameter_value(node.pass_thru.name, value)
                node._propagate_forwards()

    def _use_incoming_source_parameter_types(self) -> None:
        if self.incoming_source_parameter is None:
            msg = "Invalid state: self.incoming_source_parameter must not be None"
            raise ValueError(msg)
        self.pass_thru.input_types = [ParameterTypeBuiltin.ANY.value]
        self.pass_thru.type = self.incoming_source_parameter.output_type
        self.pass_thru.output_type = self.incoming_source_parameter.output_type

    def _to_outgoing_target_parameters_key(
        self, outgoing_target_node: BaseNode, outgoing_target_parameter: Parameter
    ) -> str:
        node_name = outgoing_target_node.name
        parameter_name = outgoing_target_parameter.name
        return f"{node_name}__{parameter_name}"

    def _add_outgoing_target_parameter(
        self, outgoing_target_node: BaseNode, outgoing_target_parameter: Parameter
    ) -> None:
        key = self._to_outgoing_target_parameters_key(outgoing_target_node, outgoing_target_parameter)
        self.outgoing_target_parameters[key] = outgoing_target_parameter

    def _remove_outgoing_target_parameter(
        self, outgoing_target_node: BaseNode, outgoing_target_parameter: Parameter
    ) -> None:
        key = self._to_outgoing_target_parameters_key(outgoing_target_node, outgoing_target_parameter)
        del self.outgoing_target_parameters[key]

    def _reset_parameter_types(self) -> None:
        self.pass_thru.input_types = [ParameterTypeBuiltin.ANY.value]
        self.pass_thru.type = None
        self.pass_thru.output_type = ParameterTypeBuiltin.ALL.value

    def _use_outgoing_target_parameters_type_intersection(self) -> None:
        if len(self.outgoing_target_parameters) == 0:
            msg = "Invalid state: self.outgoing_target_parameters must have at least one entry"
            raise ValueError(msg)

        # 1. Determine the set of input types that all the output target parameters have in common.

        # The input types, should be the overlap / intersection of
        # the currently outbound connections.
        input_type_sets = [set(p.input_types or []) for p in self.outgoing_target_parameters.values()]

        # Handle edge case: one of the input_type_sets contains 'Any'.
        #
        # Remove any input_type_sets that contain the special 'Any' type.
        # Since they match anything, they don't need to be part of the intersection.
        # A better solution would actually be to check subtype relationships, but
        # I feel like such a solution is out of scope of this PR and really should be
        # done everywhere.
        input_type_sets = [s for s in input_type_sets if not contains_any(s)]

        if input_type_sets:
            input_types = list(set.intersection(*input_type_sets))
        else:
            # If we removed everything, then they could have only contained the builtin any type.
            input_types = [ParameterTypeBuiltin.ANY.value]
        self.pass_thru.input_types = input_types

        # Determine the type. The one selected must be compatible with all
        # of the current outbound connections. All of the input_types meet
        # this requirement, so just pick one, any one.
        self.pass_thru.type = input_types[0]
        self.pass_thru.output_type = self.pass_thru.type

    def _ensure_output_uses_all_instead_of_any(self) -> None:
        # Output types use a special ALL value instead of "Any".
        if self.pass_thru.output_type.lower() == ParameterTypeBuiltin.ANY.value:
            self.pass_thru.output_type = ParameterTypeBuiltin.ALL.value
