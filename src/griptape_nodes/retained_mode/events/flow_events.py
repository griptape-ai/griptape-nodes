from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass(kw_only=True)
@PayloadRegistry.register
class CreateFlowRequest(RequestPayload):
    parent_flow_name: str | None
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class CreateFlowResultSuccess(ResultPayloadSuccess):
    flow_name: str


@dataclass
@PayloadRegistry.register
class CreateFlowResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteFlowRequest(RequestPayload):
    flow_name: str


@dataclass
@PayloadRegistry.register
class DeleteFlowResultSuccess(ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class DeleteFlowResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListNodesInFlowRequest(RequestPayload):
    flow_name: str


@dataclass
@PayloadRegistry.register
class ListNodesInFlowResultSuccess(ResultPayloadSuccess):
    node_names: list[str]


@dataclass
@PayloadRegistry.register
class ListNodesInFlowResultFailure(ResultPayloadFailure):
    pass


# Gives a list of the flows directly parented by the node specified.
@dataclass
@PayloadRegistry.register
class ListFlowsInFlowRequest(RequestPayload):
    # Pass in None to get the canvas.
    parent_flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class ListFlowsInFlowResultSuccess(ResultPayloadSuccess):
    flow_names: list[str]


@dataclass
@PayloadRegistry.register
class ListFlowsInFlowResultFailure(ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GetTopLevelFlowRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class GetTopLevelFlowResultSuccess(ResultPayloadSuccess):
    flow_name: str


@dataclass
@PayloadRegistry.register
class GetTopLevelFlowResultFailure(ResultPayloadFailure):
    pass
