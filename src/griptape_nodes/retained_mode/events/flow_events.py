from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayload_Failure,
    ResultPayload_Success,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass(kw_only=True)
@PayloadRegistry.register
class CreateFlowRequest(RequestPayload):
    parent_flow_name: str | None
    flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class CreateFlowResult_Success(ResultPayload_Success):
    flow_name: str


@dataclass
@PayloadRegistry.register
class CreateFlowResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class DeleteFlowRequest(RequestPayload):
    flow_name: str


@dataclass
@PayloadRegistry.register
class DeleteFlowResult_Success(ResultPayload_Success):
    pass


@dataclass
@PayloadRegistry.register
class DeleteFlowResult_Failure(ResultPayload_Failure):
    pass


@dataclass
@PayloadRegistry.register
class ListNodesInFlowRequest(RequestPayload):
    flow_name: str


@dataclass
@PayloadRegistry.register
class ListNodesInFlowResult_Success(ResultPayload_Success):
    node_names: list[str]


@dataclass
@PayloadRegistry.register
class ListNodesInFlowResult_Failure(ResultPayload_Failure):
    pass


# Gives a list of the flows directly parented by the node specified.
@dataclass
@PayloadRegistry.register
class ListFlowsInFlowRequest(RequestPayload):
    # Pass in None to get the canvas.
    parent_flow_name: str | None = None


@dataclass
@PayloadRegistry.register
class ListFlowsInFlowResult_Success(ResultPayload_Success):
    flow_names: list[str]


@dataclass
@PayloadRegistry.register
class ListFlowsInFlowResult_Failure(ResultPayload_Failure):
    pass
