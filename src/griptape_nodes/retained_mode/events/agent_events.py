from dataclasses import dataclass, field

from griptape.memory.structure import Run

from griptape_nodes.retained_mode.events.base_events import (
    ExecutionPayload,
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
class RunAgentRequestArtifact(dict):
    type: str
    value: str


@dataclass
@PayloadRegistry.register
class RunAgentRequest(RequestPayload):
    """Run an agent with input and optional artifacts.

    Use when: Executing conversational AI interactions, processing user queries,
    running autonomous agents, handling multi-modal inputs with URLs.

    Args:
        input: Text input to send to the agent
        url_artifacts: List of URL artifacts to include with the request
        thread_id: Thread ID to use for conversation.
        additional_mcp_servers: List of additional MCP server names to include

    Results: RunAgentResultStarted -> RunAgentResultSuccess (with output) | RunAgentResultFailure (execution error)
    """

    input: str
    url_artifacts: list[RunAgentRequestArtifact]
    thread_id: str
    additional_mcp_servers: list[str] = field(default_factory=list)


@dataclass
@PayloadRegistry.register
class RunAgentResultStarted(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Agent execution started successfully. Execution will continue asynchronously."""


@dataclass
@PayloadRegistry.register
class RunAgentResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Agent execution completed successfully.

    Args:
        output: Dictionary containing agent response and execution results
        thread_id: The thread ID used for this conversation
    """

    output: dict
    thread_id: str


@dataclass
@PayloadRegistry.register
class RunAgentResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Agent execution failed.

    Args:
        error: Dictionary containing error details and failure information
    """

    error: dict


@dataclass
@PayloadRegistry.register
class GetConversationMemoryRequest(RequestPayload):
    """Get the agent's conversation memory.

    Use when: Reviewing conversation history, implementing memory inspection,
    debugging agent behavior, displaying conversation context.

    Args:
        thread_id: Thread ID to retrieve memory from.

    Results: GetConversationMemoryResultSuccess (with runs) | GetConversationMemoryResultFailure (memory error)
    """

    thread_id: str


@dataclass
@PayloadRegistry.register
class GetConversationMemoryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Conversation memory retrieved successfully.

    Args:
        runs: List of conversation runs (exchanges between user and agent)
        thread_id: The thread ID for this conversation memory
    """

    runs: list[Run]
    thread_id: str


@dataclass
@PayloadRegistry.register
class GetConversationMemoryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Conversation memory retrieval failed. Common causes: memory not initialized, access error."""


@dataclass
@PayloadRegistry.register
class ConfigureAgentRequest(RequestPayload):
    """Configure agent settings and behavior.

    Use when: Setting up agent parameters, changing model configurations,
    customizing agent behavior, updating agent settings.

    Args:
        prompt_driver: Dictionary of prompt driver configuration options

    Results: ConfigureAgentResultSuccess | ConfigureAgentResultFailure (configuration error)
    """

    prompt_driver: dict = field(default_factory=dict)


@dataclass
@PayloadRegistry.register
class ConfigureAgentResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Agent configured successfully. New settings are now active."""


@dataclass
@PayloadRegistry.register
class ConfigureAgentResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Agent configuration failed. Common causes: invalid parameters, configuration error."""


@dataclass
@PayloadRegistry.register
class CreateThreadRequest(RequestPayload):
    """Create a new conversation thread.

    Use when: Starting a new conversation, initializing thread storage,
    creating named conversation contexts.

    Args:
        title: Optional title for the thread. If not provided, will be auto-generated from first message.
        local_id: Optional local identifier to store in thread metadata.

    Results: CreateThreadResultSuccess (with thread_id) | CreateThreadResultFailure (creation error)
    """

    title: str | None = None
    local_id: str | None = None


@dataclass
@PayloadRegistry.register
class CreateThreadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Thread created successfully.

    Args:
        thread_id: Unique identifier for the created thread
        title: Thread title (may be None if not provided and no messages yet)
        created_at: ISO timestamp when thread was created
        updated_at: ISO timestamp when thread was last updated
    """

    thread_id: str
    title: str | None
    created_at: str
    updated_at: str


@dataclass
@PayloadRegistry.register
class CreateThreadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Thread creation failed. Common causes: storage error, invalid parameters."""


@dataclass
@PayloadRegistry.register
class ListThreadsRequest(RequestPayload):
    """List all conversation threads.

    Use when: Displaying thread list, retrieving available conversations,
    implementing thread selection UI.

    Results: ListThreadsResultSuccess (with threads) | ListThreadsResultFailure (retrieval error)
    """


@dataclass
class ThreadMetadata:
    """Metadata for a conversation thread."""

    thread_id: str
    title: str | None
    created_at: str
    updated_at: str
    message_count: int
    archived: bool
    local_id: str | None = None


@dataclass
@PayloadRegistry.register
class ListThreadsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Threads retrieved successfully.

    Args:
        threads: List of thread metadata objects
    """

    threads: list[ThreadMetadata]


@dataclass
@PayloadRegistry.register
class ListThreadsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Thread listing failed. Common causes: storage error, permission error."""


@dataclass
@PayloadRegistry.register
class DeleteThreadRequest(RequestPayload):
    """Delete a conversation thread permanently.

    Use when: Removing unwanted conversations, cleaning up storage,
    implementing thread deletion UI.

    Args:
        thread_id: ID of the thread to delete

    Results: DeleteThreadResultSuccess | DeleteThreadResultFailure (deletion error)
    """

    thread_id: str


@dataclass
@PayloadRegistry.register
class DeleteThreadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Thread deleted successfully.

    Args:
        thread_id: ID of the deleted thread
    """

    thread_id: str


@dataclass
@PayloadRegistry.register
class DeleteThreadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Thread deletion failed. Common causes: thread not found, storage error."""


@dataclass
@PayloadRegistry.register
class RenameThreadRequest(RequestPayload):
    """Rename an existing thread.

    Use when: Updating thread titles, organizing conversations,
    implementing thread editing UI.

    Args:
        thread_id: ID of the thread to rename
        new_title: New title for the thread

    Results: RenameThreadResultSuccess | RenameThreadResultFailure (rename error)
    """

    thread_id: str
    new_title: str


@dataclass
@PayloadRegistry.register
class RenameThreadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Thread renamed successfully.

    Args:
        thread_id: ID of the renamed thread
        title: New title of the thread
        updated_at: ISO timestamp when thread was updated
    """

    thread_id: str
    title: str
    updated_at: str


@dataclass
@PayloadRegistry.register
class RenameThreadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Thread rename failed. Common causes: thread not found, storage error."""


@dataclass
@PayloadRegistry.register
class ArchiveThreadRequest(RequestPayload):
    """Archive a conversation thread.

    Use when: Organizing conversations, hiding inactive threads,
    cleaning up thread list without permanently deleting.

    Args:
        thread_id: ID of the thread to archive

    Results: ArchiveThreadResultSuccess | ArchiveThreadResultFailure (archive error)
    """

    thread_id: str


@dataclass
@PayloadRegistry.register
class ArchiveThreadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Thread archived successfully.

    Args:
        thread_id: ID of the archived thread
        updated_at: ISO timestamp when thread was updated
    """

    thread_id: str
    updated_at: str


@dataclass
@PayloadRegistry.register
class ArchiveThreadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Thread archive failed. Common causes: thread not found, already archived, storage error."""


@dataclass
@PayloadRegistry.register
class UnarchiveThreadRequest(RequestPayload):
    """Unarchive a conversation thread.

    Use when: Restoring archived conversations, resuming old threads,
    making archived threads active again.

    Args:
        thread_id: ID of the thread to unarchive

    Results: UnarchiveThreadResultSuccess | UnarchiveThreadResultFailure (unarchive error)
    """

    thread_id: str


@dataclass
@PayloadRegistry.register
class UnarchiveThreadResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """Thread unarchived successfully.

    Args:
        thread_id: ID of the unarchived thread
        updated_at: ISO timestamp when thread was updated
    """

    thread_id: str
    updated_at: str


@dataclass
@PayloadRegistry.register
class UnarchiveThreadResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """Thread unarchive failed. Common causes: thread not found, not archived, storage error."""


@dataclass
@PayloadRegistry.register
class AgentStreamEvent(ExecutionPayload):
    """Streaming token event during agent execution.

    Use when: Implementing real-time agent output, displaying progressive responses,
    building streaming UIs, monitoring agent token generation.

    Args:
        token: Individual token generated by the agent during execution
    """

    token: str
