from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from enum import StrEnum, auto
from typing import Any, TypeVar

from griptape.events import BaseEvent, EventBus

from griptape_nodes.exe_types.core_types import (
    BaseNodeElement,
    ControlParameterInput,
    ControlParameterOutput,
    Parameter,
    ParameterContainer,
    ParameterDictionary,
    ParameterGroup,
    ParameterList,
    ParameterMode,
    ParameterTypeBuiltin,
)
from griptape_nodes.exe_types.type_validator import TypeValidator
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionEvent,
    ExecutionGriptapeNodeEvent,
    ProgressEvent,
)
from griptape_nodes.retained_mode.events.execution_events import (
    NodeUnresolvedEvent,
    ParameterValueUpdateEvent,
)
from griptape_nodes.retained_mode.events.parameter_events import (
    RemoveParameterFromNodeRequest,
)

logger = logging.getLogger("griptape_nodes")

T = TypeVar("T")

AsyncResult = Generator[Callable[[], T], T]


class NodeResolutionState(StrEnum):
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
        self.name = name
        self.state = state
        if metadata is None:
            self.metadata = {}
        else:
            self.metadata = metadata
        self.parameter_values = {}
        self.parameter_output_values = {}
        self.root_ui_element = BaseNodeElement()
        self.process_generator = None

    # This is gross and we need to have a universal pass on resolution state changes and emission of events. That's what this ticket does!
    # https://github.com/griptape-ai/griptape-nodes/issues/994
    def make_node_unresolved(self, current_states_to_trigger_change_event: set[NodeResolutionState] | None) -> None:
        # See if the current state is in the set of states to trigger a change event.
        if current_states_to_trigger_change_event is not None and self.state in current_states_to_trigger_change_event:
            # Trigger the change event.
            # Send an event to the GUI so it knows this node has changed resolution state.
            EventBus.publish_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=NodeUnresolvedEvent(node_name=self.name))
                )
            )
        self.state = NodeResolutionState.UNRESOLVED

    def allow_incoming_connection(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
    ) -> bool:
        """Callback to confirm allowing a Connection coming TO this Node."""
        return True

    def allow_outgoing_connection(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002,
    ) -> bool:
        """Callback to confirm allowing a Connection going OUT of this Node."""
        return True

    def after_incoming_connection(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002,
        modified_parameters_set: set[str],  # noqa: ARG002
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        return

    def after_outgoing_connection(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
        modified_parameters_set: set[str],  # noqa: ARG002
    ) -> None:
        """Callback after a Connection has been established OUT of this Node."""
        return

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
        modified_parameters_set: set[str],  # noqa: ARG002
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        return

    def after_outgoing_connection_removed(
        self,
        source_parameter: Parameter,  # noqa: ARG002
        target_node: BaseNode,  # noqa: ARG002
        target_parameter: Parameter,  # noqa: ARG002
        modified_parameters_set: set[str],  # noqa: ARG002
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
        if any(char.isspace() for char in param.name):
            msg = f"Failed to add Parameter `{param.name}`. Parameter names cannot currently any whitespace characters. Please see https://github.com/griptape-ai/griptape-nodes/issues/714 to check the status on a remedy for this issue."
            raise ValueError(msg)
        if self.does_name_exist(param.name):
            msg = "Cannot have duplicate names on parameters."
            raise ValueError(msg)
        self.add_node_element(param)

    def remove_parameter(self, param: Parameter) -> None:
        for child in param.find_elements_by_type(Parameter):
            self.remove_node_element(child)
        self.remove_node_element(param)

    def remove_group_by_name(self, group: str) -> bool:
        group_items = self.root_ui_element.find_elements_by_type(ParameterGroup)
        for group_item in group_items:
            if group_item.group_name == group:
                for child in group_item.find_elements_by_type(BaseNodeElement):
                    self.remove_node_element(child)
                self.remove_node_element(group_item)
                return True
        return False

    def get_group_by_name_or_element_id(self, group: str) -> ParameterGroup | None:
        group_items = self.root_ui_element.find_elements_by_type(ParameterGroup)
        for group_item in group_items:
            if group in (group_item.group_name, group_item.element_id):
                return group_item
        return None

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
                and ParameterTypeBuiltin.CONTROL_TYPE.value not in parameter.input_types
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
        if self.current_spotlight_parameter is not None and self.current_spotlight_parameter.next is not None:
            self.current_spotlight_parameter = self.current_spotlight_parameter.next
            return True
        self.current_spotlight_parameter = None
        return False

    def get_parameter_by_element_id(self, param_element_id: str) -> Parameter | None:
        candidate = self.root_ui_element.find_element_by_id(element_id=param_element_id)
        if (candidate is not None) and (isinstance(candidate, Parameter)):
            return candidate
        return None

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
        modified_parameters: set[str] = set()

        # Allow custom node logic to prepare and possibly mutate the value before it is actually set.
        # Record any parameters modified for cascading.
        final_value = self.before_value_set(
            parameter=parameter,
            value=candidate_value,
            modified_parameters_set=modified_parameters,
        )
        # ACTUALLY SET THE NEW VALUE
        self.parameter_values[param_name] = final_value
        # If a parameter value has been set at the top level of a container, wipe all children.
        # Allow custom node logic to respond after it's been set. Record any modified parameters for cascading.
        self.after_value_set(
            parameter=parameter,
            value=final_value,
            modified_parameters_set=modified_parameters,
        )
        # handle with container parameters
        if parameter.parent_container_name is not None:
            # Does it have a parent container
            parent_parameter = self.get_parameter_by_name(parameter.parent_container_name)
            # Does the parent container exist
            if parent_parameter is not None:
                # Get it's new value dependent on it's children
                new_parent_value = handle_container_parameter(self, parent_parameter)
                if new_parent_value is not None:
                    # set that new value if it exists.
                    modified_parameters_from_container = self.set_parameter_value(
                        parameter.parent_container_name, new_parent_value
                    )
                    # Return the complete set of modified parameters.
                    if modified_parameters_from_container:
                        modified_parameters = modified_parameters | modified_parameters_from_container
        return modified_parameters

    def kill_parameter_children(self, parameter: Parameter) -> None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        for child in parameter.find_elements_by_type(Parameter):
            GriptapeNodes.handle_request(RemoveParameterFromNodeRequest(parameter_name=child.name, node_name=self.name))

    def get_parameter_value(self, param_name: str) -> Any:
        if param_name in self.parameter_values:
            return self.parameter_values[param_name]
        param = self.get_parameter_by_name(param_name)
        if param:
            value = handle_container_parameter(self, param)
            if value:
                return value
        return param.default_value if param else None

    def remove_parameter_value(self, param_name: str) -> None:
        parameter = self.get_parameter_by_name(param_name)
        if parameter is None:
            err = f"Attempted to remove value for Parameter '{param_name}' but parameter doesn't exist."
            raise KeyError(err)
        if param_name in self.parameter_values:
            del self.parameter_values[param_name]
            # special handling if it's in a container.
            if parameter.parent_container_name and parameter.parent_container_name in self.parameter_values:
                del self.parameter_values[parameter.parent_container_name]
                new_val = self.get_parameter_value(parameter.parent_container_name)
                if new_val is not None:
                    self.set_parameter_value(parameter.parent_container_name, new_val)
        else:
            err = f"Attempted to remove value for Parameter '{param_name}' but no value was set."
            raise KeyError(err)

    def get_next_control_output(self) -> Parameter | None:
        for param in self.parameters:
            if (
                ParameterTypeBuiltin.CONTROL_TYPE.value == param.output_type
                and ParameterMode.OUTPUT in param.allowed_modes
            ):
                return param
        return None

    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/852
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
        if value is not None:
            return value

        # Try fallback if value is invalid or empty
        if fallback is None:
            return None
        self.set_parameter_value(param_name, fallback)
        # No valid options available
        return fallback

    # Abstract method to process the node. Must be defined by the type
    # Must save the values of the output parameters in NodeContext.
    @abstractmethod
    def process[T](self) -> AsyncResult | None:
        pass

    # if not implemented, it will return no issues.
    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Runs before the entire workflow is run."""
        return None

    def validate_before_node_run(self) -> list[Exception] | None:
        """Runs before this node is run."""
        return None

    # It could be quite common to want to validate whether or not a parameter is empty.
    # this helper function can be used within the `validate_before_workflow_run` method along with other validations
    #
    # Example:
    """
    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = []
        prompt_error = self.validate_empty_parameter(param="prompt", additional_msg="Please provide a prompt to generate an image.")
        if prompt_error:
            exceptions.append(prompt_error)
        return exceptions if exceptions else None
    """

    def validate_empty_parameter(self, param: str, additional_msg: str = "") -> Exception | None:
        param_value = self.parameter_values.get(param, None)
        node_name = self.name
        if not param_value or param_value.isspace():
            msg = str(f"Parameter \"{param}\" was left blank for node '{node_name}'. {additional_msg}").strip()
            return ValueError(msg)
        return None

    def get_config_value(self, service: str, value: str) -> str:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        config_value = GriptapeNodes.ConfigManager().get_config_value(f"nodes.{service}.{value}")
        return config_value

    def set_config_value(self, service: str, value: str, new_value: str) -> None:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        GriptapeNodes.ConfigManager().set_config_value(f"nodes.{service}.{value}", new_value)

    def clear_node(self) -> None:
        # set state to unresolved
        self.state = NodeResolutionState.UNRESOLVED
        # delete all output values potentially generated
        self.parameter_output_values.clear()
        # Remove the current spotlight
        while self.current_spotlight_parameter is not None:
            temp = self.current_spotlight_parameter.next
            del self.current_spotlight_parameter
            self.current_spotlight_parameter = temp

    def append_value_to_parameter(self, parameter_name: str, value: Any) -> None:
        # Add the value to the node
        if parameter_name in self.parameter_output_values:
            try:
                self.parameter_output_values[parameter_name] = self.parameter_output_values[parameter_name] + value
            except TypeError:
                try:
                    self.parameter_output_values[parameter_name].append(value)
                except Exception as e:
                    msg = f"Value is not appendable to parameter '{parameter_name}' on {self.name}"
                    raise RuntimeError(msg) from e
        else:
            self.parameter_output_values[parameter_name] = value
        # Publish the event up!
        EventBus.publish_event(ProgressEvent(value=value, node_name=self.name, parameter_name=parameter_name))

    def publish_update_to_parameter(self, parameter_name: str, value: Any) -> None:
        parameter = self.get_parameter_by_name(parameter_name)
        if parameter:
            data_type = parameter.type
            self.parameter_output_values[parameter_name] = value
            payload = ParameterValueUpdateEvent(
                node_name=self.name,
                parameter_name=parameter_name,
                data_type=data_type,
                value=TypeValidator.safe_serialize(value),
            )
            EventBus.publish_event(ExecutionGriptapeNodeEvent(wrapped_event=ExecutionEvent(payload=payload)))
        else:
            msg = f"Parameter '{parameter_name} doesn't exist on {self.name}'"
            raise RuntimeError(msg)


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
            if (
                ParameterTypeBuiltin.CONTROL_TYPE.value == param.output_type
                and ParameterMode.OUTPUT in param.allowed_modes
            ):
                return param
        return None


class DataNode(BaseNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata=metadata)


class StartNode(BaseNode):
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(ControlParameterOutput())


class EndNode(BaseNode):
    # TODO: https://github.com/griptape-ai/griptape-nodes/issues/854
    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)
        self.add_parameter(ControlParameterInput())


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


def handle_container_parameter(current_node: BaseNode, parameter: Parameter) -> Any:
    """Process container parameters and build appropriate data structures.

    This function handles ParameterContainer objects by collecting values from their child
    parameters and constructing either a list or dictionary based on the container type.

    Args:
        current_node: The node containing parameter values
        parameter: The parameter to process, which may be a container

    Returns:
        A list of parameter values if parameter is a ParameterContainer,
        or None if the parameter is not a container
    """
    # if it's a container and it's value isn't already set.
    if isinstance(parameter, ParameterContainer):
        children = parameter.find_elements_by_type(Parameter, find_recursively=False)
        if isinstance(parameter, ParameterList):
            build_parameter_value = []
        elif isinstance(parameter, ParameterDictionary):
            build_parameter_value = {}
        build_parameter_value = []
        for child in children:
            value = current_node.get_parameter_value(child.name)
            if value is not None:
                build_parameter_value.append(value)
        return build_parameter_value
    return None
