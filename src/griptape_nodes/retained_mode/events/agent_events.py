from dataclasses import dataclass

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
class ConfigureAgentPromptDriverRequest(RequestPayload):
    model: str | None = None


@dataclass
@PayloadRegistry.register
class ConfigureAgentPromptDriverResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class ConfigureAgentPromptDriverResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ConfigureAgentConversationMemoryRequest(RequestPayload):
    reset_conversation_memory: bool = False


@dataclass
@PayloadRegistry.register
class ConfigureAgentConversationMemoryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    pass


@dataclass
@PayloadRegistry.register
class ConfigureAgentConversationMemoryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
