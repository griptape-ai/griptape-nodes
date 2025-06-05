from dataclasses import dataclass, field

from griptape.memory.structure import Run

from griptape_nodes.retained_mode.events.base_events import (
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class RunAgentRequest(RequestPayload):
    input: str


@dataclass
@PayloadRegistry.register
class RunAgentResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    output: str


@dataclass
@PayloadRegistry.register
class RunAgentResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    error: str


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
class ConfigureAgentRequest(RequestPayload):
    prompt_driver: dict = field(default_factory=dict)


@dataclass
@PayloadRegistry.register
class ConfigureAgentResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class ConfigureAgentResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ResetAgentConversationMemoryRequest(RequestPayload):
    pass


@dataclass
@PayloadRegistry.register
class ResetAgentConversationMemoryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class ResetAgentConversationMemoryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
