from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NamedTuple

from pydantic import Field

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class AddParameterToNodeRequest(RequestPayload):
    node_name: str
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

    @classmethod
    def create(cls, **kwargs) -> AddParameterToNodeRequest:
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


@dataclass
@PayloadRegistry.register
class AddParameterToNodeResultSuccess(ResultPayloadSuccess):
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
    node_name: str


@dataclass
@PayloadRegistry.register
class RemoveParameterFromNodeResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class RemoveParameterFromNodeResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class SetParameterValueRequest(RequestPayload):
    parameter_name: str
    node_name: str
    value: Any
    data_type: str | None = None


@dataclass
@PayloadRegistry.register
class SetParameterValueResultSuccess(ResultPayloadSuccess):
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
    node_name: str


@dataclass
@PayloadRegistry.register
class GetParameterDetailsResultSuccess(ResultPayloadSuccess):
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
class GetParameterDetailsResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class AlterParameterDetailsRequest(RequestPayload):
    parameter_name: str
    node_name: str
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


@dataclass
@PayloadRegistry.register
class AlterParameterDetailsResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class AlterParameterDetailsResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetParameterValueRequest(RequestPayload):
    parameter_name: str
    node_name: str


@dataclass
@PayloadRegistry.register
class GetParameterValueResultSuccess(ResultPayloadSuccess):
    input_types: list[str]
    type: str
    output_type: str
    value: Any


@dataclass
@PayloadRegistry.register
class GetParameterValueResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class OnParameterValueChanged(ResultPayloadSuccess):
    node_name: str
    parameter_name: str
    data_type: str
    value: Any


@dataclass
@PayloadRegistry.register
class GetCompatibleParametersRequest(RequestPayload):
    node_name: str
    parameter_name: str
    is_output: bool


class ParameterAndMode(NamedTuple):
    parameter_name: str
    is_output: bool


@dataclass
@PayloadRegistry.register
class GetCompatibleParametersResultSuccess(ResultPayloadSuccess):
    valid_parameters_by_node: dict[str, list[ParameterAndMode]]


@dataclass
@PayloadRegistry.register
class GetCompatibleParametersResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetNodeElementDetailsRequest(RequestPayload):
    node_name: str
    specific_element_id: str | None = None  # Pass None to use the root


@dataclass
@PayloadRegistry.register
class GetNodeElementDetailsResultSuccess(ResultPayloadSuccess):
    element_details: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetNodeElementDetailsResultFailure(ResultPayloadFailure):
    pass
