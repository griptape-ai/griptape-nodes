from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NamedTuple

from pydantic import Field

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.retained_mode.events.base_events import (
    ExecutionPayload,
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class AddParameterToNodeRequest(RequestPayload):
    """Add a new parameter to a node.

    Use when: Dynamically adding inputs/outputs to nodes, customizing node interfaces,
    building configurable nodes. Supports type validation, tooltips, and mode restrictions.

    Results: AddParameterToNodeResultSuccess (with parameter name) | AddParameterToNodeResultFailure
    """

    # If node name is None, use the Current Context
    node_name: str | None = None
    parameter_name: str | None = None
    default_value: Any | None = None
    tooltip: str | list[dict] | None = None
    tooltip_as_input: str | list[dict] | None = None
    tooltip_as_property: str | list[dict] | None = None
    tooltip_as_output: str | list[dict] | None = None
    type: str | None = None
    input_types: list[str] | None = None
    output_type: str | None = None
    ui_options: dict | None = None
    mode_allowed_input: bool = Field(default=True)
    mode_allowed_property: bool = Field(default=True)
    mode_allowed_output: bool = Field(default=True)
    parent_container_name: str | None = None
    # initial_setup prevents unnecessary work when we are loading a workflow from a file.
    initial_setup: bool = False

    @classmethod
    def create(cls, **kwargs) -> AddParameterToNodeRequest:
        if "name" in kwargs:
            name = kwargs.pop("name")
            kwargs["parameter_name"] = name
        known_attrs = {k: v for k, v in kwargs.items() if k in cls.__annotations__}
        # Create instance with known attributes and extra_attrs dict
        instance = cls(**known_attrs)
        return instance


@dataclass
@PayloadRegistry.register
class AddParameterToNodeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Parameter added successfully to node.

    Args:
        parameter_name: Name of the new parameter
        type: Type of the parameter
        node_name: Name of the node parameter was added to
    """

    parameter_name: str
    type: str
    node_name: str


@dataclass
@PayloadRegistry.register
class AddParameterToNodeResultFailure(ResultPayloadFailure):
    """Parameter addition failed. Common causes: node not found, invalid parameter name, type conflicts."""


@dataclass
@PayloadRegistry.register
class RemoveParameterFromNodeRequest(RequestPayload):
    """Remove a parameter from a node.

    Use when: Cleaning up unused parameters, dynamically restructuring node interfaces,
    removing deprecated parameters. Handles cleanup of connections and values.

    Results: RemoveParameterFromNodeResultSuccess | RemoveParameterFromNodeResultFailure
    """

    parameter_name: str
    # If node name is None, use the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class RemoveParameterFromNodeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Parameter removed successfully from node. Connections and values cleaned up."""


@dataclass
@PayloadRegistry.register
class RemoveParameterFromNodeResultFailure(ResultPayloadFailure):
    """Parameter removal failed. Common causes: node not found, parameter not found, removal not allowed."""


@dataclass
@PayloadRegistry.register
class SetParameterValueRequest(RequestPayload):
    """Set the value of a parameter on a node.

    Use when: Configuring node inputs, setting property values, loading saved workflows,
    updating parameter values programmatically. Handles type validation and conversion.

    Results: SetParameterValueResultSuccess (with finalized value) | SetParameterValueResultFailure
    """

    parameter_name: str
    value: Any
    # If node name is None, use the Current Context
    node_name: str | None = None
    data_type: str | None = None
    # initial_setup prevents unnecessary work when we are loading a workflow from a file.
    initial_setup: bool = False
    # is_output is true when the value being saved is from an output value. Used when loading a workflow from a file.
    is_output: bool = False


@dataclass
@PayloadRegistry.register
class SetParameterValueResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Parameter value set successfully. Value may have been processed or converted.

    Args:
        finalized_value: The actual value stored after processing
        data_type: The determined data type of the value
    """

    finalized_value: Any
    data_type: str


@dataclass
@PayloadRegistry.register
class SetParameterValueResultFailure(ResultPayloadFailure):
    """Parameter value setting failed.

    Common causes: node not found, parameter not found,
    type validation error, value conversion error.
    """


@dataclass
@PayloadRegistry.register
class GetParameterDetailsRequest(RequestPayload):
    """Get detailed information about a parameter.

    Use when: Inspecting parameter configuration, validating parameter properties,
    building UIs that display parameter details, understanding parameter capabilities.

    Results: GetParameterDetailsResultSuccess (with full details) | GetParameterDetailsResultFailure
    """

    parameter_name: str
    # If node name is None, use the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetParameterDetailsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Parameter details retrieved successfully.

    Args:
        element_id: Unique identifier for the parameter
        type: Parameter type
        input_types: Accepted input types
        output_type: Output type when used as output
        default_value: Default value if any
        tooltip: General tooltip text
        tooltip_as_input/property/output: Mode-specific tooltips
        mode_allowed_input/property/output: Which modes are allowed
        is_user_defined: Whether this is a user-defined parameter
        ui_options: UI configuration options
    """

    element_id: str
    type: str
    input_types: list[str]
    output_type: str
    default_value: Any | None
    tooltip: str | list[dict]
    tooltip_as_input: str | list[dict] | None
    tooltip_as_property: str | list[dict] | None
    tooltip_as_output: str | list[dict] | None
    mode_allowed_input: bool
    mode_allowed_property: bool
    mode_allowed_output: bool
    is_user_defined: bool
    ui_options: dict | None


@dataclass
@PayloadRegistry.register
class GetParameterDetailsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Parameter details retrieval failed. Common causes: node not found, parameter not found."""


@dataclass
@PayloadRegistry.register
class AlterParameterDetailsRequest(RequestPayload):
    parameter_name: str
    # If node name is None, use the Current Context
    node_name: str | None = None
    type: str | None = None
    input_types: list[str] | None = None
    output_type: str | None = None
    default_value: Any | None = None
    tooltip: str | list[dict] | None = None
    tooltip_as_input: str | list[dict] | None = None
    tooltip_as_property: str | list[dict] | None = None
    tooltip_as_output: str | list[dict] | None = None
    mode_allowed_input: bool | None = None
    mode_allowed_property: bool | None = None
    mode_allowed_output: bool | None = None
    ui_options: dict | None = None
    traits: set[str] | None = None
    # initial_setup prevents unnecessary work when we are loading a workflow from a file.
    initial_setup: bool = False

    @classmethod
    def create(cls, **kwargs) -> AlterParameterDetailsRequest:
        if "allowed_modes" in kwargs:
            kwargs["mode_allowed_input"] = ParameterMode.INPUT in kwargs["allowed_modes"]
            kwargs["mode_allowed_output"] = ParameterMode.OUTPUT in kwargs["allowed_modes"]
            kwargs["mode_allowed_property"] = ParameterMode.PROPERTY in kwargs["allowed_modes"]
            kwargs.pop("allowed_modes")
        if "name" in kwargs:
            name = kwargs.pop("name")
            kwargs["parameter_name"] = name
        known_attrs = {k: v for k, v in kwargs.items() if k in cls.__annotations__}

        # Create instance with known attributes and extra_attrs dict
        instance = cls(**known_attrs)
        return instance

    @classmethod
    def relevant_parameters(cls) -> list[str]:
        return [
            "parameter_name",
            "node_name",
            "type",
            "input_types",
            "output_type",
            "default_value",
            "tooltip",
            "tooltip_as_input",
            "tooltip_as_property",
            "tooltip_as_output",
            "mode_allowed_input",
            "mode_allowed_property",
            "mode_allowed_output",
            "ui_options",
            "traits",
        ]


@dataclass
@PayloadRegistry.register
class AlterParameterDetailsResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class AlterParameterDetailsResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetParameterValueRequest(RequestPayload):
    """Get the current value of a parameter.

    Use when: Reading parameter values, debugging workflow state, displaying current values in UIs,
    validating parameter states before execution.

    Results: GetParameterValueResultSuccess (with value and type info) | GetParameterValueResultFailure
    """

    parameter_name: str
    # If node name is None, use the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetParameterValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Parameter value retrieved successfully.

    Args:
        input_types: Accepted input types
        type: Current parameter type
        output_type: Output type when used as output
        value: Current parameter value
    """

    input_types: list[str]
    type: str
    output_type: str
    value: Any


@dataclass
@PayloadRegistry.register
class GetParameterValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Parameter value retrieval failed. Common causes: node not found, parameter not found."""


@dataclass
@PayloadRegistry.register
class OnParameterValueChanged(WorkflowAlteredMixin, ResultPayloadSuccess):
    node_name: str
    parameter_name: str
    data_type: str
    value: Any


@dataclass
@PayloadRegistry.register
class GetCompatibleParametersRequest(RequestPayload):
    """Get parameters that are compatible for connections.

    Use when: Creating connections between nodes, validating connection compatibility,
    building connection UIs, discovering available connection targets.

    Results: GetCompatibleParametersResultSuccess (with compatible parameters) | GetCompatibleParametersResultFailure
    """

    parameter_name: str
    is_output: bool
    # If node name is None, use the Current Context
    node_name: str | None = None


class ParameterAndMode(NamedTuple):
    parameter_name: str
    is_output: bool


@dataclass
@PayloadRegistry.register
class GetCompatibleParametersResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Compatible parameters retrieved successfully.

    Args:
        valid_parameters_by_node: Dictionary mapping node names to lists of compatible parameters
    """

    valid_parameters_by_node: dict[str, list[ParameterAndMode]]


@dataclass
@PayloadRegistry.register
class GetCompatibleParametersResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Compatible parameters retrieval failed. Common causes: node not found, parameter not found."""


@dataclass
@PayloadRegistry.register
class GetNodeElementDetailsRequest(RequestPayload):
    # If node name is None, use the Current Context
    node_name: str | None = None
    specific_element_id: str | None = None  # Pass None to use the root


@dataclass
@PayloadRegistry.register
class GetNodeElementDetailsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    element_details: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetNodeElementDetailsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


# This is the same as getparameterelementdetailsrequest, might have to modify it a bit.
@dataclass
@PayloadRegistry.register
class AlterElementEvent(ExecutionPayload):
    element_details: dict[str, Any]


@dataclass
@PayloadRegistry.register
class RenameParameterRequest(RequestPayload):
    """Rename a parameter on a node.

    Use when: Refactoring parameter names, improving parameter clarity, updating parameter
    naming conventions. Handles updating connections and references.

    Results: RenameParameterResultSuccess (with old and new names) | RenameParameterResultFailure
    """

    parameter_name: str
    new_parameter_name: str
    # If node name is None, use the Current Context
    node_name: str | None = None
    # initial_setup prevents unnecessary work when we are loading a workflow from a file.
    initial_setup: bool = False


@dataclass
@PayloadRegistry.register
class RenameParameterResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """Parameter renamed successfully. Connections and references updated.

    Args:
        old_parameter_name: Previous parameter name
        new_parameter_name: New parameter name
        node_name: Name of the node containing the parameter
    """

    old_parameter_name: str
    new_parameter_name: str
    node_name: str


@dataclass
@PayloadRegistry.register
class RenameParameterResultFailure(ResultPayloadFailure):
    """Parameter rename failed.

    Common causes: node not found, parameter not found,
    name already exists, invalid new name.
    """


@dataclass
@PayloadRegistry.register
class RemoveElementEvent(ExecutionPayload):
    element_id: str
