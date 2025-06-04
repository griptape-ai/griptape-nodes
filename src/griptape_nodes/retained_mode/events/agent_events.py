from dataclasses import dataclass

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry

from griptape.memory.structure import Run


@dataclass
@PayloadRegistry.register
class RunAgentRequest(RequestPayload):
    input: str

@dataclass
@PayloadRegistry.register
class RunAgentResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass

@dataclass
@PayloadRegistry.register
class RunAgentResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass

@dataclass
@PayloadRegistry.register
class GetConversationMemoryRequest(RequestPayload):
    pass

@dataclass
@PayloadRegistry.register
class GetConversationMemoryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    runs: list[Run]

@dataclass
@PayloadRegistry.register
class GetConversationMemoryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass

@dataclass
@PayloadRegistry.register
class ResetAgentRequest(RequestPayload):
    pass

@dataclass
@PayloadRegistry.register
class ResetAgentResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass

@dataclass
@PayloadRegistry.register
class ResetAgentResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
