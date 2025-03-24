from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum, auto
from typing import Any, Self

from griptape.events import BaseEvent

from griptape_nodes.exe_types.core_types import (
    ControlParameter_Input,
    ControlParameter_Output,
    Parameter,
    ParameterControlType,
    ParameterMode,
)


class NodeResolutionState(Enum):
    """Possible states for a node during resolution."""

    UNRESOLVED = auto()
    RESOLVING = auto()
    RESOLVED = auto()


class NodeBase(ABC):
    # Owned by a flow
    name: str
    metadata: dict[Any, Any]
    parameters: list[Parameter]

    # Node Context Fields
    state: NodeResolutionState
    current_spotlight_parameter: Parameter | None = None
    parameter_values: dict[str, Any]
    parameter_output_values: dict[str, Any]
    stop_flow: bool = False
    parameter_to_callback: dict[str, Callable[[Any], list[str]]]

    def __hash__(self) -> int:
        return hash(self.name)

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
        state: NodeResolutionState = NodeResolutionState.UNRESOLVED,
    ) -> None:
        self.name = name
        self.state = state
        self.parameters = []
        if metadata is None:
            self.metadata = {}
        else:
            self.metadata = metadata
        self.parameter_values = {}
        self.parameter_output_values = {}
        self.parameter_name_to_callback = {}

    def make_node_unresolved(self) -> None:
        self.state = NodeResolutionState.UNRESOLVED

    # Callback to confirm allowing a Connection coming TO this Node.
    def allow_incoming_connection(
        self,
        source_node: Self,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> bool:
        return True

    # Callback to confirm allowing a Connection going OUT of this Node.
    def allow_outgoing_connection(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: Self,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> bool:
        return True

    def handle_incoming_connection(
        self,
        source_node: Self,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        return

    def handle_outgoing_connection(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: Self,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Callback after a Connection has been established OUT of this Node."""
        return

    def handle_incoming_connection_removed(
        self,
        source_node: Self,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        return

    def handle_outgoing_connection_removed(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: Self,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> None:
        """Callback after a Connection OUT of this Node was REMOVED."""
        return

    def on_griptape_event(self, event: BaseEvent) -> None:  # noqa: ARG002
        """Callback for when a Griptape Event comes destined for this Node."""
        return

    def does_name_exist(self, param_name: str) -> bool:
        for parameter in self.parameters:
            if parameter.name == param_name:
                return True
        return False

    # TODO(griptape): Do i need to flag control/ not control parameters?
    def add_parameter(self, param: Parameter, callback: Callable[[Any], list[str]] | None = None) -> None:
        if self.does_name_exist(param.name):
            msg = "Cannot have duplicate names on parameters."
            raise ValueError(msg)
        if callback:
            self.parameter_name_to_callback[param.name] = callback
        self.parameters.append(param)

    def remove_parameter(self, param: Parameter) -> None:
        self.parameters.remove(param)
        if param.name in self.parameter_name_to_callback:
            del self.parameter_name_to_callback[param.name]

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

    def set_parameter_value(self, param_name: str, value: Any) -> list[str] | None:
        # Actually sets the parameter value
        self.parameter_values[param_name] = value
        if param_name in self.parameter_name_to_callback:
            callback = self.parameter_name_to_callback[param_name]
            # call the callback
            # TODO(kate): Change this to be more robust if a callback doesn't return what we want
            modified_parameters = callback(value)
            return modified_parameters
        return None

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


class ControlNode(NodeBase):
    # Control Nodes may have one Control Input Port and at least one Control Output Port
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata=metadata)
        control_parameter_in = ControlParameter_Input()
        control_parameter_out = ControlParameter_Output()

        self.parameters.append(control_parameter_in)
        self.parameters.append(control_parameter_out)

    def get_next_control_output(self) -> Parameter | None:
        for param in self.parameters:
            if ParameterControlType.__name__ in param.allowed_types and ParameterMode.OUTPUT in param.allowed_modes:
                return param
        return None


class DataNode(NodeBase):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata=metadata)


class StartNode(NodeBase):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)


class EndNode(ControlNode):
    # TODO(griptape): Anything else for an EndNode?
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)


class Connection:
    source_node: NodeBase
    target_node: NodeBase
    source_parameter: Parameter
    target_parameter: Parameter

    def __init__(
        self,
        source_node: NodeBase,
        source_parameter: Parameter,
        target_node: NodeBase,
        target_parameter: Parameter,
    ) -> None:
        self.source_node = source_node
        self.target_node = target_node
        self.source_parameter = source_parameter
        self.target_parameter = target_parameter

    def get_target_node(self) -> NodeBase:
        return self.target_node

    def get_source_node(self) -> NodeBase:
        return self.source_node
