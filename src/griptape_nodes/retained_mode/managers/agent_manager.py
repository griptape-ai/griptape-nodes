"""Chat-sidebar agent manager backed by the Pydantic AI harness.

This manager owns:

  * the lifecycle of a per-process :class:`PydanticAgentRunner` that talks to
    Griptape Cloud through its OpenAI-compatible Chat Completions endpoint,
  * the local thread storage backend that persists Pydantic AI message
    history,
  * the existing engine-bundled MCP server (started here as a background
    thread, just like before),
  * the same request handlers the chat sidebar already calls
    (``RunAgentRequest``, ``ConfigureAgentRequest``, the thread CRUD set,
    ``GetConversationMemoryRequest``, ``ListAgentModelsRequest``).

The Griptape ``Agent`` and the JSON-output parsing dance it required are gone.
Streaming tokens come straight off Pydantic AI's text deltas via the runner's
``token_sink`` callback and land on the UI as ``AgentStreamEvent`` payloads.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.usage import UsageLimits
from xdg_base_dirs import xdg_data_home

from griptape_nodes.agents.pydantic_ai.mcp_servers import mcp_server_from_config, streamable_http_local
from griptape_nodes.agents.pydantic_ai.runner import (
    PydanticAgentRunner,
    RunEvent,
    TextDelta,
    ThinkingDelta,
    ToolCall,
    ToolResult,
)
from griptape_nodes.agents.pydantic_ai.workspace_tools import WorkspaceToolsetConfig
from griptape_nodes.drivers.cloud_models import (
    DEPRECATED_MODELS,
    IMAGE_DEPRECATED_MODELS,
    IMAGE_MODEL_CHOICES,
    MODEL_CHOICES,
)
from griptape_nodes.drivers.thread_storage.local_thread_storage_driver import LocalThreadStorageDriver
from griptape_nodes.retained_mode.events.agent_events import (
    AgentStreamEvent,
    AgentThinkingEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    ArchiveThreadRequest,
    ArchiveThreadResultFailure,
    ArchiveThreadResultSuccess,
    CancelAgentRequest,
    CancelAgentResultFailure,
    CancelAgentResultSuccess,
    ConfigureAgentRequest,
    ConfigureAgentResultFailure,
    ConfigureAgentResultSuccess,
    CreateThreadRequest,
    CreateThreadResultFailure,
    CreateThreadResultSuccess,
    DeleteThreadRequest,
    DeleteThreadResultFailure,
    DeleteThreadResultSuccess,
    GetConversationMemoryRequest,
    GetConversationMemoryResultFailure,
    GetConversationMemoryResultSuccess,
    ListAgentModelsRequest,
    ListAgentModelsResultSuccess,
    ListThreadsRequest,
    ListThreadsResultFailure,
    ListThreadsResultSuccess,
    RenameThreadRequest,
    RenameThreadResultFailure,
    RenameThreadResultSuccess,
    RunAgentRequest,
    RunAgentResultFailure,
    RunAgentResultSuccess,
    UnarchiveThreadRequest,
    UnarchiveThreadResultFailure,
    UnarchiveThreadResultSuccess,
)
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.base_events import ExecutionEvent, ExecutionGriptapeNodeEvent, ResultPayload
from griptape_nodes.retained_mode.events.mcp_events import (
    GetEnabledMCPServersRequest,
    GetEnabledMCPServersResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.config_manager import ConfigManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
from griptape_nodes.servers import bind_free_socket
from griptape_nodes.servers.mcp import GTN_MCP_SERVER_HOST, GTN_MCP_SERVER_PORT, start_mcp_server

if TYPE_CHECKING:
    from pydantic_ai.toolsets import AbstractToolset

    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.static_files_manager import StaticFilesManager


logger = logging.getLogger("griptape_nodes")

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"

config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)


DEFAULT_AGENT_INSTRUCTIONS = (
    "You are a coding assistant embedded in Griptape Nodes. You operate by calling tools.\n\n"
    "Tools available to you:\n"
    "  - Workspace file tools: read_file, write_file, edit_file, glob_files, grep_files, shell. "
    "Use these to read, write, search, and run code inside the user's workspace.\n"
    "  - GriptapeNodes MCP tools (prefixed `GriptapeNodes_`). Use these to interact with the "
    "engine: list libraries and node types, create nodes, set parameter values, wire "
    "connections, save and run workflows.\n\n"
    "Behavior rules (these are non-negotiable):\n"
    "  1. NEVER respond with only a plan or a description of what you intend to do. If a "
    "     task requires tool work, call the relevant tools in the SAME turn as your "
    "     acknowledgment. A response of the form 'I'll do X' with no tool calls is wrong.\n"
    "  2. When the user asks you to build, create, modify, inspect, or run something, "
    "     start with discovery tool calls (e.g. ListRegisteredLibrariesRequest, "
    "     ListNodeTypesInLibraryRequest, glob_files, read_file) before doing anything that "
    "     mutates state.\n"
    "  3. Make multiple tool calls in parallel when they don't depend on each other.\n"
    "  4. Only after you have actually completed the user's task should you produce a final "
    "     text response. That final response should be a short summary of what you did, "
    "     including the names of any nodes/files you created or changed.\n"
)

# Cap each chat-sidebar turn so a runaway loop can't burn through credits or
# wedge the conversation. The numbers are deliberately generous: 60 model
# requests is enough for a complex multi-tool task while still protecting the
# user from a tool-call loop.
DEFAULT_AGENT_USAGE_LIMITS = UsageLimits(request_limit=60)


@dataclass
class _ActiveRun:
    """Handle to an in-flight agent run, used to deliver cancellation.

    ``cancel_event`` belongs to ``loop`` (the loop the run awaits on). A
    ``CancelAgentRequest`` may be handled on a different loop (skip-the-line
    requests run on the websocket loop), so the event is always set via
    ``loop.call_soon_threadsafe`` rather than touched directly.
    """

    cancel_event: asyncio.Event
    loop: asyncio.AbstractEventLoop


class AgentManager:
    """Owns the chat-sidebar agent runner and the engine-bundled MCP server."""

    def __init__(self, static_files_manager: StaticFilesManager, event_manager: EventManager | None = None) -> None:
        self.static_files_manager = static_files_manager
        self._mcp_server_port = GTN_MCP_SERVER_PORT
        self._model_name: str = MODEL_CHOICES[0] if MODEL_CHOICES else "gpt-4o"
        self._instructions: str = DEFAULT_AGENT_INSTRUCTIONS

        self._threads_dir: Path = xdg_data_home() / "griptape_nodes" / "threads"
        self._thread_storage: LocalThreadStorageDriver = LocalThreadStorageDriver(
            self._threads_dir, config_manager, secrets_manager
        )

        # Cache one runner per (model, mcp-set) tuple; rebuild when either changes.
        self._runner_cache: dict[tuple[str, tuple[str, ...]], PydanticAgentRunner] = {}

        # Cancel handles for in-flight runs, keyed by thread_id. A CancelAgentRequest
        # signals the event; the run races it and unwinds. Populated for the duration
        # of each run only.
        self._active_runs: dict[str, _ActiveRun] = {}

        if event_manager is not None:
            event_manager.assign_manager_to_request_type(RunAgentRequest, self.on_handle_run_agent_request)
            event_manager.assign_manager_to_request_type(CancelAgentRequest, self.on_handle_cancel_agent_request)
            event_manager.assign_manager_to_request_type(ConfigureAgentRequest, self.on_handle_configure_agent_request)
            event_manager.assign_manager_to_request_type(
                GetConversationMemoryRequest, self.on_handle_get_conversation_memory_request
            )

            event_manager.assign_manager_to_request_type(CreateThreadRequest, self.on_handle_create_thread_request)
            event_manager.assign_manager_to_request_type(ListThreadsRequest, self.on_handle_list_threads_request)
            event_manager.assign_manager_to_request_type(DeleteThreadRequest, self.on_handle_delete_thread_request)
            event_manager.assign_manager_to_request_type(RenameThreadRequest, self.on_handle_rename_thread_request)
            event_manager.assign_manager_to_request_type(ArchiveThreadRequest, self.on_handle_archive_thread_request)
            event_manager.assign_manager_to_request_type(
                UnarchiveThreadRequest, self.on_handle_unarchive_thread_request
            )
            event_manager.assign_manager_to_request_type(
                ListAgentModelsRequest, self.on_handle_list_agent_models_request
            )

            event_manager.add_listener_to_app_event(
                AppInitializationComplete,
                self.on_app_initialization_complete,
            )

    # --- App lifecycle ----------------------------------------------------

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        api_key = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)
        sock = bind_free_socket(GTN_MCP_SERVER_HOST, GTN_MCP_SERVER_PORT)
        self._mcp_server_port = sock.getsockname()[1]
        threading.Thread(target=start_mcp_server, args=(api_key, sock), daemon=True, name="mcp-server").start()

    # --- Run agent --------------------------------------------------------

    async def on_handle_run_agent_request(self, request: RunAgentRequest) -> ResultPayload:
        try:
            return await self._run_agent(request)
        except Exception as e:
            err_msg = f"Error running agent: {e}"
            logger.exception(err_msg)
            return RunAgentResultFailure(error={"message": str(e)}, result_details=err_msg)

    async def _run_agent(self, request: RunAgentRequest) -> ResultPayload:
        thread_id = self._validate_thread_for_run(request.thread_id)
        is_first_run = len(self._thread_storage.load_history(thread_id)) == 0

        runner = self._build_runner(request.additional_mcp_servers)
        prompt = _compose_prompt(request.input, request.url_artifacts)

        event_manager = GriptapeNodes.EventManager()

        def emit(event: RunEvent) -> None:
            payload = _run_event_to_payload(event)
            if payload is None:
                return
            event_manager.put_event(
                ExecutionGriptapeNodeEvent(
                    wrapped_event=ExecutionEvent(payload=payload),
                ),
            )

        cancel_event = asyncio.Event()
        self._active_runs[thread_id] = _ActiveRun(cancel_event=cancel_event, loop=asyncio.get_running_loop())
        try:
            result = await runner.run(prompt, thread_id=thread_id, event_sink=emit, cancel_event=cancel_event)
        finally:
            # Only drop our own entry; a newer run for the same thread may have
            # replaced it (shouldn't happen for the chat sidebar, but stay safe).
            if (active := self._active_runs.get(thread_id)) is not None and active.cancel_event is cancel_event:
                del self._active_runs[thread_id]

        if result.cancelled:
            logger.info("Agent run for thread %s cancelled by request.", result.thread_id)
            return RunAgentResultSuccess(
                output={"text": result.output, "message_count": result.message_count, "cancelled": True},
                thread_id=result.thread_id,
                result_details="Agent run cancelled.",
            )

        if is_first_run:
            self._thread_storage.update_thread_metadata(
                result.thread_id, title=_generate_title_from_input(request.input)
            )

        return RunAgentResultSuccess(
            output={"text": result.output, "message_count": result.message_count, "cancelled": False},
            thread_id=result.thread_id,
            result_details="Agent execution completed successfully.",
        )

    def on_handle_cancel_agent_request(self, request: CancelAgentRequest) -> ResultPayload:
        """Signal cooperative cancellation to the in-flight run for a thread.

        Idempotent: returns success even when no run is active so the UI can fire
        cancel without first checking run state. ``was_running`` distinguishes
        the two cases.
        """
        try:
            active = self._active_runs.get(request.thread_id)
            if active is None:
                return CancelAgentResultSuccess(
                    thread_id=request.thread_id,
                    was_running=False,
                    result_details=f"No active agent run for thread {request.thread_id}.",
                )
            # The run awaits on active.loop, which may differ from the loop handling
            # this (skip-the-line) request; asyncio.Event is not thread-safe, so hop.
            active.loop.call_soon_threadsafe(active.cancel_event.set)
            return CancelAgentResultSuccess(
                thread_id=request.thread_id,
                was_running=True,
                result_details=f"Cancellation signalled for thread {request.thread_id}.",
            )
        except Exception as e:
            details = f"Error cancelling agent run: {e}"
            logger.exception(details)
            return CancelAgentResultFailure(result_details=details)

    # --- Thread CRUD -----------------------------------------------------

    def on_handle_create_thread_request(self, request: CreateThreadRequest) -> ResultPayload:
        try:
            thread_id, meta = self._thread_storage.create_thread(title=request.title, local_id=request.local_id)
            return CreateThreadResultSuccess(
                thread_id=thread_id,
                title=meta.get("title"),
                created_at=meta["created_at"],
                updated_at=meta["updated_at"],
                result_details="Thread created successfully.",
            )
        except Exception as e:
            details = f"Error creating thread: {e}"
            logger.exception(details)
            return CreateThreadResultFailure(result_details=details)

    def on_handle_list_threads_request(self, _: ListThreadsRequest) -> ResultPayload:
        try:
            threads = self._thread_storage.list_threads()
            return ListThreadsResultSuccess(threads=threads, result_details="Threads retrieved successfully.")
        except Exception as e:
            details = f"Error listing threads: {e}"
            logger.exception(details)
            return ListThreadsResultFailure(result_details=details)

    def on_handle_delete_thread_request(self, request: DeleteThreadRequest) -> ResultPayload:
        try:
            self._thread_storage.delete_thread(request.thread_id)
            return DeleteThreadResultSuccess(thread_id=request.thread_id, result_details="Thread deleted successfully.")
        except ValueError as e:
            details = str(e)
            logger.error(details)
            return DeleteThreadResultFailure(result_details=details)
        except Exception as e:
            details = f"Error deleting thread: {e}"
            logger.exception(details)
            return DeleteThreadResultFailure(result_details=details)

    def on_handle_rename_thread_request(self, request: RenameThreadRequest) -> ResultPayload:
        try:
            if not self._thread_storage.thread_exists(request.thread_id):
                details = f"Thread {request.thread_id} not found"
                logger.error(details)
                return RenameThreadResultFailure(result_details=details)

            updated_meta = self._thread_storage.update_thread_metadata(request.thread_id, title=request.new_title)
            return RenameThreadResultSuccess(
                thread_id=request.thread_id,
                title=updated_meta["title"],
                updated_at=updated_meta["updated_at"],
                result_details="Thread renamed successfully.",
            )
        except Exception as e:
            details = f"Error renaming thread: {e}"
            logger.exception(details)
            return RenameThreadResultFailure(result_details=details)

    def on_handle_archive_thread_request(self, request: ArchiveThreadRequest) -> ResultPayload:
        try:
            if not self._thread_storage.thread_exists(request.thread_id):
                details = f"Thread {request.thread_id} not found"
                logger.error(details)
                return ArchiveThreadResultFailure(result_details=details)

            meta = self._thread_storage.get_thread_metadata(request.thread_id)
            if meta.get("archived", False):
                details = f"Thread {request.thread_id} is already archived"
                logger.error(details)
                return ArchiveThreadResultFailure(result_details=details)

            updated_meta = self._thread_storage.update_thread_metadata(request.thread_id, archived=True)
            return ArchiveThreadResultSuccess(
                thread_id=request.thread_id,
                updated_at=updated_meta["updated_at"],
                result_details="Thread archived successfully.",
            )
        except Exception as e:
            details = f"Error archiving thread: {e}"
            logger.exception(details)
            return ArchiveThreadResultFailure(result_details=details)

    def on_handle_unarchive_thread_request(self, request: UnarchiveThreadRequest) -> ResultPayload:
        try:
            if not self._thread_storage.thread_exists(request.thread_id):
                details = f"Thread {request.thread_id} not found"
                logger.error(details)
                return UnarchiveThreadResultFailure(result_details=details)

            meta = self._thread_storage.get_thread_metadata(request.thread_id)
            if not meta.get("archived", False):
                details = f"Thread {request.thread_id} is not archived"
                logger.error(details)
                return UnarchiveThreadResultFailure(result_details=details)

            updated_meta = self._thread_storage.update_thread_metadata(request.thread_id, archived=False)
            return UnarchiveThreadResultSuccess(
                thread_id=request.thread_id,
                updated_at=updated_meta["updated_at"],
                result_details="Thread unarchived successfully.",
            )
        except Exception as e:
            details = f"Error unarchiving thread: {e}"
            logger.exception(details)
            return UnarchiveThreadResultFailure(result_details=details)

    # --- Configuration / inspection -------------------------------------

    def on_handle_configure_agent_request(self, request: ConfigureAgentRequest) -> ResultPayload:
        """Update agent configuration. Currently honors only `model` for the prompt driver.

        ``image_generation_driver`` settings are accepted but ignored: the new
        runner does not provide an in-band image-generation tool yet. The chat
        sidebar can still send the request without erroring.
        """
        try:
            if "model" in request.prompt_driver:
                new_model = str(request.prompt_driver["model"])
                if new_model != self._model_name:
                    self._model_name = new_model
                    self._runner_cache.clear()
        except Exception as e:
            details = f"Error configuring agent: {e}"
            logger.exception(details)
            return ConfigureAgentResultFailure(result_details=details)
        return ConfigureAgentResultSuccess(result_details="Agent configured successfully.")

    def on_handle_list_agent_models_request(self, _: ListAgentModelsRequest) -> ResultPayload:
        return ListAgentModelsResultSuccess(
            prompt_models=list(MODEL_CHOICES),
            image_models=list(IMAGE_MODEL_CHOICES),
            deprecated_models={**DEPRECATED_MODELS, **IMAGE_DEPRECATED_MODELS},
            result_details="Agent model lists retrieved successfully.",
        )

    def on_handle_get_conversation_memory_request(self, request: GetConversationMemoryRequest) -> ResultPayload:
        try:
            history = self._thread_storage.load_history(request.thread_id)
            messages = ModelMessagesTypeAdapter.dump_python(history, mode="json")
            return GetConversationMemoryResultSuccess(
                messages=messages,
                thread_id=request.thread_id,
                result_details="Conversation memory retrieved successfully.",
            )
        except Exception as e:
            details = f"Error getting conversation memory: {e}"
            logger.exception(details)
            return GetConversationMemoryResultFailure(result_details=details)

    # --- Internal helpers -----------------------------------------------

    def _build_runner(self, additional_mcp_servers: list[str]) -> PydanticAgentRunner:
        cache_key = (self._model_name, tuple(sorted(additional_mcp_servers)))
        if (cached := self._runner_cache.get(cache_key)) is not None:
            return cached

        api_key = secrets_manager.get_secret(API_KEY_ENV_VAR)
        if not api_key:
            msg = f"Secret '{API_KEY_ENV_VAR}' not found"
            raise ValueError(msg)

        workspace_root = Path(config_manager.workspace_path)
        mcp_servers: list[AbstractToolset[Any]] = [
            streamable_http_local(
                f"http://localhost:{self._mcp_server_port}/mcp/",
                name="GriptapeNodes",
            ),
        ]
        for cfg in self._lookup_mcp_configs(additional_mcp_servers):
            built = mcp_server_from_config(cfg["name"], cfg)
            if built is not None:
                mcp_servers.append(built)

        runner = PydanticAgentRunner(
            model_name=self._model_name,
            api_key=api_key,
            workspace_root=workspace_root,
            storage=self._thread_storage,
            instructions=self._instructions,
            workspace_config=WorkspaceToolsetConfig(workspace_root=workspace_root),
            mcp_servers=mcp_servers,
            usage_limits=DEFAULT_AGENT_USAGE_LIMITS,
        )
        self._runner_cache[cache_key] = runner
        return runner

    @staticmethod
    def _lookup_mcp_configs(server_names: list[str]) -> list[dict[str, Any]]:
        if not server_names:
            return []
        result = GriptapeNodes.handle_request(GetEnabledMCPServersRequest())
        if not isinstance(result, GetEnabledMCPServersResultSuccess):
            logger.warning("Could not load enabled MCP servers; agent will run without extras.")
            return []
        return [{**result.servers[name], "name": name} for name in server_names if name in result.servers]

    def _validate_thread_for_run(self, thread_id: str | None) -> str:
        if thread_id is None or not self._thread_storage.thread_exists(thread_id):
            new_id, _ = self._thread_storage.create_thread()
            return new_id

        meta = self._thread_storage.get_thread_metadata(thread_id)
        if meta.get("archived", False):
            details = f"Cannot run agent on archived thread {thread_id}. Unarchive it first."
            raise ValueError(details)
        return thread_id


def _compose_prompt(text: str, url_artifacts: list[Any]) -> str:
    """Combine the plain text input with any attached URL artifacts.

    The new runner's prompt is ``str``-only at the surface; we render URL
    artifacts as bracketed markers so the model still sees what was attached.
    Once the model adapter exposes binary user content, this will route image
    URLs through Pydantic AI's ``ImageUrl`` type instead.
    """
    if not url_artifacts:
        return text
    extras: list[str] = []
    for artifact in url_artifacts:
        url = artifact.get("value") if isinstance(artifact, dict) else None
        kind = artifact.get("type") if isinstance(artifact, dict) else None
        if url:
            extras.append(f"[{kind or 'attachment'}: {url}]")
    if not extras:
        return text
    return text + "\n\nAttachments:\n" + "\n".join(extras)


def _generate_title_from_input(user_input: str, max_length: int = 50) -> str:
    if len(user_input) <= max_length:
        return user_input
    return user_input[:max_length].rsplit(" ", 1)[0] + "..."


def _run_event_to_payload(event: RunEvent) -> Any:
    """Translate a runner event into the matching ExecutionPayload.

    Returns ``None`` for event kinds that don't have a UI counterpart yet.
    """
    if isinstance(event, TextDelta):
        return AgentStreamEvent(token=event.delta)
    if isinstance(event, ToolCall):
        return AgentToolCallEvent(
            tool_call_id=event.tool_call_id,
            tool_name=event.tool_name,
            args=event.args,
        )
    if isinstance(event, ToolResult):
        return AgentToolResultEvent(
            tool_call_id=event.tool_call_id,
            tool_name=event.tool_name,
            content=event.content,
            is_error=event.is_error,
        )
    if isinstance(event, ThinkingDelta):
        return AgentThinkingEvent(delta=event.delta)
    return None
