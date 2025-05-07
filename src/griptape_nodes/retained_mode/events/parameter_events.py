from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NamedTuple

from pydantic import Field

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
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
    parameter_name: str
    type: str
    node_name: str


@dataclass
@PayloadRegistry.register
class AddParameterToNodeResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class RemoveParameterFromNodeRequest(RequestPayload):
    parameter_name: str
    # If node name is None, use the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class RemoveParameterFromNodeResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class RemoveParameterFromNodeResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SetParameterValueRequest(RequestPayload):
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
    finalized_value: Any
    data_type: str


@dataclass
@PayloadRegistry.register
class SetParameterValueResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetParameterDetailsRequest(RequestPayload):
    parameter_name: str
    # If node name is None, use the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetParameterDetailsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
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
    pass


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
    parameter_name: str
    # If node name is None, use the Current Context
    node_name: str | None = None


@dataclass
@PayloadRegistry.register
class GetParameterValueResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    input_types: list[str]
    type: str
    output_type: str
    value: Any


@dataclass
@PayloadRegistry.register
class GetParameterValueResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


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
    valid_parameters_by_node: dict[str, list[ParameterAndMode]]


@dataclass
@PayloadRegistry.register
class GetCompatibleParametersResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


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
class AlterParameterEvent(ExecutionPayload):
    node_name: str
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

    # TODO: Get known_attrs dynamically, instead of setting manually. https://github.com/griptape-ai/griptape-nodes/issues/1039
    @classmethod
    def create(cls, node_name: str, parameter: Parameter) -> AlterParameterEvent:
        known_attrs = {
            "node_name": node_name,
            "element_id": parameter.element_id,
            "type": parameter.type,
            "input_types": parameter.input_types,
            "output_type": parameter.output_type,
            "default_value": parameter.default_value,
            "tooltip": parameter.tooltip,
            "tooltip_as_input": parameter.tooltip_as_input,
            "tooltip_as_property": parameter.tooltip_as_property,
            "tooltip_as_output": parameter.tooltip_as_output,
            "mode_allowed_input": ParameterMode.INPUT in parameter.allowed_modes,
            "mode_allowed_property": ParameterMode.PROPERTY in parameter.allowed_modes,
            "mode_allowed_output": ParameterMode.OUTPUT in parameter.allowed_modes,
            "is_user_defined": parameter.user_defined,
            "ui_options": parameter.ui_options,
        }
        # Create instance with known attributes and extra_attrs dict
        instance = cls(**known_attrs)
        return instance
