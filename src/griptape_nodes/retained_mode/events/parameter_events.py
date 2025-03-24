from dataclasses import dataclass
from typing import Any

from pydantic import Field

from griptape_nodes.exe_types.core_types import ParameterMode, ParameterUIOptions
from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayload_Failure,
    ResultPayload_Success,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class AddParameterToNodeRequest(RequestPayload):
    parameter_name: str
    node_name: str
    allowed_types: list[str]
    default_value: Any | None
    tooltip: str
    tooltip_as_input: str | None = None
    tooltip_as_property: str | None = None
    tooltip_as_output: str | None = None
    ui_options: ParameterUIOptions | None = None
    mode_allowed_input: bool = Field(default=True)
    mode_allowed_property: bool = Field(default=True)
    mode_allowed_output: bool = Field(default=True)

    @classmethod
    def create(cls, **kwargs) -> "AddParameterToNodeRequest":
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
class AddParameterToNodeResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class AddParameterToNodeResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class RemoveParameterFromNodeRequest(RequestPayload):
    parameter_name: str
    node_name: str


@dataclass
@PayloadRegistry.register
class RemoveParameterFromNodeResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class RemoveParameterFromNodeResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class SetParameterValueRequest(RequestPayload):
    parameter_name: str
    node_name: str
    value: Any


@dataclass
@PayloadRegistry.register
class SetParameterValueResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class SetParameterValueResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class GetParameterDetailsRequest(RequestPayload):
    parameter_name: str
    node_name: str


@dataclass
@PayloadRegistry.register
class GetParameterDetailsResult_Success(ResultPayload_Success):
    allowed_types: list[str]
    default_value: Any | None
    tooltip: str
    tooltip_as_input: str | None
    tooltip_as_property: str | None
    tooltip_as_output: str | None
    mode_allowed_input: bool
    mode_allowed_property: bool
    mode_allowed_output: bool
    is_user_defined: bool
    ui_options: ParameterUIOptions | None


@dataclass
@PayloadRegistry.register
class GetParameterDetailsResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class AlterParameterDetailsRequest(RequestPayload):
    parameter_name: str
    node_name: str
    allowed_types: list[str] | None = None
    default_value: Any | None = None
    tooltip: str | None = None
    tooltip_as_input: str | None = None
    tooltip_as_property: str | None = None
    tooltip_as_output: str | None = None
    mode_allowed_input: bool | None = None
    mode_allowed_property: bool | None = None
    mode_allowed_output: bool | None = None
    ui_options: ParameterUIOptions | None = None

    @classmethod
    def create(cls, **kwargs) -> "AlterParameterDetailsRequest":
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
class AlterParameterDetailsResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class AlterParameterDetailsResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class GetParameterValueRequest(RequestPayload):
    parameter_name: str
    node_name: str


@dataclass
@PayloadRegistry.register
class GetParameterValueResult_Success(ResultPayload_Success):
    data_type: str
    value: Any


@dataclass
@PayloadRegistry.register
class GetParameterValueResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class OnParameterValueChanged(ResultPayload_Success):
    node_name: str
    parameter_name: str
    data_type: str
    value: Any
