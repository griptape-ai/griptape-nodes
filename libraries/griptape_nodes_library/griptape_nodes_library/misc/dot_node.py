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


class DotNode(DataNode):
    # Track the incoming and outgoing connections to choose our allowed types.
    value: Parameter

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        self.value = Parameter(
            name="value",
            input_types=[ParameterTypeBuiltin.ANY.value],
            output_type=ParameterTypeBuiltin.ALL.value,
            default_value=None,
            tooltip="Pass-through value",
            allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            hide_property=True,
        )
        self.add_parameter(self.value)

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
            return
        self._remove_outgoing_target_parameter(target_node, target_parameter)
        self._propagate_backwards()

    def process(self) -> None:
        self.parameter_output_values["value"] = self.parameter_values.get("value")

    def _resolve_types(self) -> None:
        if self.incoming_source_parameter is not None and len(self.outgoing_target_parameters) > 0:
            self._use_outgoing_target_parameters_type_intersection()
            self.value.type = self.incoming_source_parameter.type
            self.value.output_type = self.incoming_source_parameter.output_type
        elif self.incoming_source_parameter is not None:
            self._use_incoming_source_parameter_types()
        elif len(self.outgoing_target_parameters) > 0:
            self._use_outgoing_target_parameters_type_intersection()
        else:
            self._reset_parameter_types()

        self._ensure_output_uses_all_instead_of_any()

    def _propagate_backwards(self) -> None:
        self._resolve_types()
        incoming_node = None
        if self.incoming_source_parameter is not None:
            incoming_node = self.incoming_source_parameter.get_node()
        if isinstance(incoming_node, self.__class__):
            incoming_node._propagate_backwards()
        else:
            self._propagate_forwards()

    def _propagate_forwards(self) -> None:
        self._resolve_types()
        for param in self.outgoing_target_parameters.values():
            node = param.get_node()
            if node and isinstance(node, self.__class__):
                value = self.get_parameter_value(self.value.name)
                node.set_parameter_value(node.value.name, value)
                node._propagate_forwards()

    def _use_incoming_source_parameter_types(self) -> None:
        if self.incoming_source_parameter is None:
            msg = "Invalid state: self.incoming_source_parameter must not be None"
            raise ValueError(msg)
        self.value.input_types = [ParameterTypeBuiltin.ANY.value]
        self.value.type = self.incoming_source_parameter.output_type
        self.value.output_type = self.incoming_source_parameter.output_type

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
        self.value.input_types = [ParameterTypeBuiltin.ANY.value]
        self.value.type = None
        self.value.output_type = ParameterTypeBuiltin.ALL.value

    def _use_outgoing_target_parameters_type_intersection(self) -> None:
        if len(self.outgoing_target_parameters) == 0:
            msg = "Invalid state: self.outgoing_target_parameters must have at least one entry"
            raise ValueError(msg)

        input_type_sets = [set(p.input_types or []) for p in self.outgoing_target_parameters.values()]

        input_type_sets = [s for s in input_type_sets if not contains_any(s)]

        if input_type_sets:
            input_types = list(set.intersection(*input_type_sets))
        else:
            input_types = [ParameterTypeBuiltin.ANY.value]
        self.value.input_types = input_types

        self.value.type = input_types[0]
        self.value.output_type = self.value.type

    def _ensure_output_uses_all_instead_of_any(self) -> None:
        if self.value.output_type.lower() == ParameterTypeBuiltin.ANY.value:
            self.value.output_type = ParameterTypeBuiltin.ALL.value
