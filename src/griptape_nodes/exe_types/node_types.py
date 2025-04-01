from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Self

from griptape.events import BaseEvent

from griptape_nodes.exe_types.core_types import (
    BaseNodeElement,
    ControlParameterInput,
    ControlParameterOutput,
    Parameter,
    ParameterControlType,
    ParameterMode,
)


class NodeResolutionState(Enum):
    """Possible states for a node during resolution."""

    UNRESOLVED = auto()
    RESOLVING = auto()
    RESOLVED = auto()


class BaseNode(ABC):
    # Owned by a flow
    name: str
    metadata: dict[Any, Any]

    # Node Context Fields
    state: NodeResolutionState
    current_spotlight_parameter: Parameter | None = None
    parameter_values: dict[str, Any]
    parameter_output_values: dict[str, Any]
    stop_flow: bool = False
    root_ui_element: BaseNodeElement

    @property
    def parameters(self) -> list[Parameter]:
        return self.root_ui_element.find_elements_by_type(Parameter)

    def __hash__(self) -> int:
        return hash(self.name)

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        state: NodeResolutionState = NodeResolutionState.UNRESOLVED,
    ) -> None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        self.name = name
        self.state = state
        if metadata is None:
            self.metadata = {}
        else:
            self.metadata = metadata
        self.parameter_values = {}
        self.parameter_output_values = {}
        self.root_ui_element = BaseNodeElement()
        self.config_manager = GriptapeNodes.ConfigManager()

    def make_node_unresolved(self) -> None:
        self.state = NodeResolutionState.UNRESOLVED

    def allow_incoming_connection(
        self,
        source_node: Self,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> bool:
        """Callback to confirm allowing a Connection coming TO this Node."""
        return True

    def allow_outgoing_connection(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: Self,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> bool:
        """Callback to confirm allowing a Connection going OUT of this Node."""
        return True

    def after_incoming_connection(
        self,
        source_node: Self,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        return

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: Self,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Callback after a Connection has been established OUT of this Node."""
        return

    def after_incoming_connection_removed(
        self,
        source_node: Self,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        return

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: Self,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Callback after a Connection OUT of this Node was REMOVED."""
        return

    def before_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> Any:  # noqa: ARG002
        """Callback when a Parameter's value is ABOUT to be set.

        Custom nodes may elect to override the default behavior by implementing this function in their node code.

        This gives the node an opportunity to perform custom logic before a parameter is set. This may result in:
          * Further mutating the value that would be assigned to the Parameter
          * Mutating other Parameters or state within the Node

        If other Parameters are changed, the engine needs a list of which
        ones have changed to cascade unresolved state.

        Args:
            parameter: the Parameter on this node that is about to be changed
            value: the value intended to be set (this has already gone through any converters and validators on the Parameter)
            modified_parameters_set: A set of parameter names within this node that were modified as a result
                of this call. The Parameter this was called on does NOT need to be part of the return.

        Returns:
            The final value to set for the Parameter. This gives the Node logic one last opportunity to mutate the value
            before it is assigned.
        """
        # Default behavior is to do nothing to the supplied value, and indicate no other modified Parameters.
        return value

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:  # noqa: ARG002
        """Callback AFTER a Parameter's value was set.

        Custom nodes may elect to override the default behavior by implementing this function in their node code.

        This gives the node an opportunity to perform custom logic after a parameter is set. This may result in
        changing other Parameters on the node. If other Parameters are changed, the engine needs a list of which
        ones have changed to cascade unresolved state.

        Args:
            parameter: the Parameter on this node that was just changed
            value: the value that was set (already converted, validated, and possibly mutated by the node code)
            modified_parameters_set: A set of parameter names within this node that were modified as a result
                of this call. The Parameter this was called on does NOT need to be part of the return.

        Returns:
            Nothing
        """
        # Default behavior is to do nothing, and indicate no other modified Parameters.
        return None  # noqa: RET501

    def on_griptape_event(self, event: BaseEvent) -> None:  # noqa: ARG002
        """Callback for when a Griptape Event comes destined for this Node."""
        return

    def does_name_exist(self, param_name: str) -> bool:
        for parameter in self.parameters:
            if parameter.name == param_name:
                return True
        return False

    def add_parameter(self, param: Parameter) -> None:
        """Adds a Parameter to the Node. Control and Data Parameters are all treated equally."""
        if self.does_name_exist(param.name):
            msg = "Cannot have duplicate names on parameters."
            raise ValueError(msg)
        self.add_node_element(param)

    def remove_parameter(self, param: Parameter) -> None:
        self.remove_node_element(param)

    def add_node_element(self, ui_element: BaseNodeElement) -> None:
        self.root_ui_element.add_child(ui_element)

    def remove_node_element(self, ui_element: BaseNodeElement) -> None:
        self.root_ui_element.remove_child(ui_element)

    def get_current_parameter(self) -> Parameter | None:
        return self.current_spotlight_parameter

    def initialize_spotlight(self) -> None:
        # Make a deep copy of all of the parameters and create the linked list.
        curr_param = None
        prev_param = None
        for parameter in self.parameters:
            if (
                ParameterMode.INPUT in parameter.get_mode()
                and ParameterControlType.__name__ not in parameter.allowed_types
            ):
                if not self.current_spotlight_parameter or prev_param is None:
                    # make a copy of the parameter and assign it to current spotlight
                    param_copy = parameter.copy()
                    self.current_spotlight_parameter = param_copy
                    prev_param = param_copy
                    # go on to the next one because prev and next don't need to be set yet.
                    continue
                # prev_param will have been initialized at this point
                curr_param = parameter.copy()
                prev_param.next = curr_param
                curr_param.prev = prev_param
                prev_param = curr_param

    # Advance the current index to the next index
    def advance_parameter(self) -> bool:
        if self.current_spotlight_parameter and self.current_spotlight_parameter.next is not None:
            self.current_spotlight_parameter = self.current_spotlight_parameter.next
            return True
        self.current_spotlight_parameter = None
        return False

    def get_parameter_by_name(self, param_name: str) -> Parameter | None:
        for parameter in self.parameters:
            if param_name == parameter.name:
                return parameter
        return None

    def set_parameter_value(self, param_name: str, value: Any) -> set[str] | None:
        """Attempt to set a Parameter's value.

        The Node may choose to store a different value (or type) than what was passed in.
        Conversion callbacks on the Parameter may raise Exceptions, which will cancel
        the value assignment. Similarly, validator callbacks may reject the value and
        raise an Exception.

        Exceptions should be handled by the caller; this may result in canceling
        a running Flow or forcing an upstream object to alter its assumptions.

        Changing a Parameter may trigger other Parameters within the Node
        to be changed. If other Parameters are changed, the engine needs a list of which
        ones have changed to cascade unresolved state.

        Args:
            param_name: the name of the Parameter on this node that is about to be changed
            value: the value intended to be set

        Returns:
            A set of parameter names within this node that were modified as a result
            of this assignment. The Parameter this was called on does NOT need to be
            part of the return.
        """
        parameter = self.get_parameter_by_name(param_name)
        if parameter is None:
            err = f"Attempted to set value for Parameter '{param_name}' but no such Parameter could be found."
            raise KeyError(err)
        # Perform any conversions to the value based on how the Parameter is configured.
        # THESE MAY RAISE EXCEPTIONS. These can cause a running Flow to be canceled, or
        # cause a calling object to alter its assumptions/behavior. The value requested
        # to be assigned will NOT be set.
        candidate_value = value
        for converter in parameter.converters:
            candidate_value = converter(candidate_value)

        # Validate the values next, based on how the Parameter is configured.
        # THESE MAY RAISE EXCEPTIONS. These can cause a running Flow to be canceled, or
        # cause a calling object to alter its assumptions/behavior. The value requested
        # to be assigned will NOT be set.
        for validator in parameter.validators:
            validator(parameter, candidate_value)

        # Keep track of which other parameters got modified as a result of any node-specific logic.
        modified_parameters = set()

        # Allow custom node logic to prepare and possibly mutate the value before it is actually set.
        # Record any parameters modified for cascading.
        final_value = self.before_value_set(
            parameter=parameter, value=candidate_value, modified_parameters_set=modified_parameters
        )

        # ACTUALLY SET THE NEW VALUE
        self.parameter_values[param_name] = final_value

        # Allow custom node logic to respond after it's been set. Record any modified parameters for cascading.
        self.after_value_set(parameter=parameter, value=final_value, modified_parameters_set=modified_parameters)

        # Return the complete set of modified parameters.
        return modified_parameters

    def get_parameter_value(self, param_name: str) -> Any:
        return self.parameter_values[param_name]

    def get_next_control_output(self) -> Parameter | None:
        for param in self.parameters:
            if ParameterControlType.__name__ in param.allowed_types and ParameterMode.OUTPUT in param.allowed_modes:
                return param
        return None

    def valid_or_fallback(self, param_name: str, fallback: Any = None) -> Any:
        """Get a parameter value if valid, otherwise use fallback.

        Args:
            param_name: The name of the parameter to check
            fallback: The fallback value to use if the parameter value is invalid or empty

        Returns:
            The valid parameter value or fallback

        Raises:
            ValueError: If neither the parameter value nor fallback is valid
        """
        # Get parameter object and current value
        param = self.get_parameter_by_name(param_name)
        if not param:
            msg = f"Parameter '{param_name}' not found"
            raise ValueError(msg)

        value = self.parameter_values.get(param_name, None)

        # Check if value is empty or not allowed
        if value is None:
            is_empty = True
            is_valid = False
        else:
            is_empty = value is None or (isinstance(value, str) and not value.strip())
            is_valid = param.is_value_allowed(value)

        # Return value if it's valid and not empty
        if is_valid and not is_empty:
            return value

        # Try fallback if value is invalid or empty
        if fallback is None:
            return None
        if param.is_value_allowed(fallback):
            # Store the fallback value in parameter_values for future use
            self.parameter_values[param_name] = fallback
            return fallback

        # No valid options available
        return None

    # Abstract method to process the node. Must be defined by the type
    # Must save the values of the output parameters in NodeContext.
    @abstractmethod
    def process(self) -> None:
        pass

    # if not implemented, it will return no issues.
    def validate_node(self) -> list[Exception] | None:
        return None

    def get_config_value(self, service: str, value: str) -> str:
        return self.config_manager.get_config_value(f"nodes.{service}.{value}")

    def set_config_value(self, service: str, value: str, new_value: str) -> None:
        self.config_manager.set_config_value(f"nodes.{service}.{value}", new_value)


class ControlNode(BaseNode):
    # Control Nodes may have one Control Input Port and at least one Control Output Port
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata=metadata)
        control_parameter_in = ControlParameterInput()
        control_parameter_out = ControlParameterOutput()

        self.add_parameter(control_parameter_in)
        self.add_parameter(control_parameter_out)

    def get_next_control_output(self) -> Parameter | None:
        for param in self.parameters:
            if ParameterControlType.__name__ in param.allowed_types and ParameterMode.OUTPUT in param.allowed_modes:
                return param
        return None


class DataNode(BaseNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata=metadata)


class StartNode(BaseNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)


class EndNode(ControlNode):
    # TODO(griptape): Anything else for an EndNode?
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)


class Connection:
    source_node: BaseNode
    target_node: BaseNode
    source_parameter: Parameter
    target_parameter: Parameter

    def __init__(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_node: BaseNode,
        target_parameter: Parameter,
    ) -> None:
        self.source_node = source_node
        self.target_node = target_node
        self.source_parameter = source_parameter
        self.target_parameter = target_parameter

    def get_target_node(self) -> BaseNode:
        return self.target_node

    def get_source_node(self) -> BaseNode:
        return self.source_node
