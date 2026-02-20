import asyncio
import json
import logging
import os
import threading
import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING, ClassVar

import requests
from attrs import define, field
from griptape.artifacts import ErrorArtifact, ImageUrlArtifact
from griptape.drivers.image_generation import BaseImageGenerationDriver
from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.events import TextChunkEvent
from griptape.loaders import ImageLoader
from griptape.memory.structure import ConversationMemory
from griptape.rules import Rule, Ruleset
from griptape.structures import Agent
from griptape.tools import BaseImageGenerationTool
from griptape.tools.mcp.tool import MCPTool
from griptape.utils.decorators import activity
from json_repair import repair_json
from pydantic import create_model
from schema import Literal, Schema
from xdg_base_dirs import xdg_data_home

from griptape_nodes.drivers.thread_storage import (
    GriptapeCloudThreadStorageDriver,
    LocalThreadStorageDriver,
)
from griptape_nodes.retained_mode.events.agent_events import (
    AgentStreamEvent,
    ArchiveThreadRequest,
    ArchiveThreadResultFailure,
    ArchiveThreadResultSuccess,
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
    ListAvailableModelsRequest,
    ListAvailableModelsResultFailure,
    ListAvailableModelsResultSuccess,
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
from griptape_nodes.retained_mode.managers.event_manager import EventManager
from griptape_nodes.retained_mode.managers.secrets_manager import SecretsManager
from griptape_nodes.retained_mode.managers.static_files_manager import (
    StaticFilesManager,
)
from griptape_nodes.servers.mcp import start_mcp_server

if TYPE_CHECKING:
    from griptape.tools.mcp.sessions import StreamableHttpConnection

logger = logging.getLogger("griptape_nodes")

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
BASE_URL = "https://cloud.griptape.ai"
CHAT_MODELS_URL = f"{BASE_URL}/api/models?model_type=chat"
IMAGE_MODELS_URL = f"{BASE_URL}/api/models?model_type=image_generation"
GTN_MCP_SERVER_PORT = int(os.getenv("GTN_MCP_SERVER_PORT", "9927"))

config_manager = ConfigManager()
secrets_manager = SecretsManager(config_manager)


@define
class NodesPromptImageGenerationTool(BaseImageGenerationTool):
    image_generation_driver: BaseImageGenerationDriver = field(kw_only=True)
    static_files_manager: StaticFilesManager = field(kw_only=True)

    @activity(
        config={
            "description": "Generates an image from text prompts. Both prompt and negative_prompt are required.",
            "schema": Schema(
                {
                    Literal("prompt", description=BaseImageGenerationTool.PROMPT_DESCRIPTION): str,
                    Literal("negative_prompt", description=BaseImageGenerationTool.NEGATIVE_PROMPT_DESCRIPTION): str,
                }
            ),
        },
    )
    def generate_image(self, params: dict[str, dict[str, str]]) -> ImageUrlArtifact | ErrorArtifact:
        prompt = params["values"]["prompt"]
        negative_prompt = params["values"]["negative_prompt"]

        output_artifact = self.image_generation_driver.run_text_to_image(
            prompts=[prompt], negative_prompts=[negative_prompt]
        )
        filename = f"{uuid.uuid4()}.png"
        image_url = self.static_files_manager.save_static_file(output_artifact.to_bytes(), filename)
        return ImageUrlArtifact(image_url)


class AgentManager:
    # Field mappings for each transport type
    TRANSPORT_FIELD_MAPPINGS: ClassVar[dict[str, list[str]]] = {
        "stdio": ["command", "args", "env", "cwd", "encoding", "encoding_error_handler"],
        "sse": ["url", "headers", "timeout", "sse_read_timeout"],
        "streamable_http": ["url", "headers", "timeout", "sse_read_timeout", "terminate_on_close"],
        "websocket": ["url"],
    }

    def __init__(self, static_files_manager: StaticFilesManager, event_manager: EventManager | None = None) -> None:
        self.prompt_driver = None
        self.image_tool = None
        self.mcp_tool = None
        self.static_files_manager = static_files_manager
        self.model_configurations = {}  # Store model configs: {model_name: {args, supports_output_schema}}

        # Thread management
        self._threads_dir = xdg_data_home() / "griptape_nodes" / "threads"
        self._threads_dir.mkdir(parents=True, exist_ok=True)

        # Initialize thread storage driver based on config
        self.thread_storage_driver = self._initialize_thread_storage_driver()

        if event_manager is not None:
            # Existing handlers
            event_manager.assign_manager_to_request_type(RunAgentRequest, self.on_handle_run_agent_request)
            event_manager.assign_manager_to_request_type(ConfigureAgentRequest, self.on_handle_configure_agent_request)
            event_manager.assign_manager_to_request_type(
                GetConversationMemoryRequest, self.on_handle_get_conversation_memory_request
            )

            # New thread management handlers
            event_manager.assign_manager_to_request_type(CreateThreadRequest, self.on_handle_create_thread_request)
            event_manager.assign_manager_to_request_type(ListThreadsRequest, self.on_handle_list_threads_request)
            event_manager.assign_manager_to_request_type(DeleteThreadRequest, self.on_handle_delete_thread_request)
            event_manager.assign_manager_to_request_type(RenameThreadRequest, self.on_handle_rename_thread_request)
            event_manager.assign_manager_to_request_type(ArchiveThreadRequest, self.on_handle_archive_thread_request)
            event_manager.assign_manager_to_request_type(
                UnarchiveThreadRequest, self.on_handle_unarchive_thread_request
            )

            # Model management handlers
            event_manager.assign_manager_to_request_type(
                ListAvailableModelsRequest, self.on_handle_list_available_models_request
            )

            event_manager.add_listener_to_app_event(
                AppInitializationComplete,
                self.on_app_initialization_complete,
            )
            # TODO: Listen for shutdown event (https://github.com/griptape-ai/griptape-nodes/issues/2149) to stop mcp server

    async def on_handle_run_agent_request(self, request: RunAgentRequest) -> ResultPayload:
        if self.prompt_driver is None:
            self.prompt_driver = self._initialize_prompt_driver()
        if self.image_tool is None:
            self.image_tool = self._initialize_image_tool()
        if self.mcp_tool is None:
            self.mcp_tool = self._initialize_mcp_tool()
        try:
            return await asyncio.to_thread(self._on_handle_run_agent_request, request)
        except Exception as e:
            err_msg = f"Error handling run agent request: {e}"
            return RunAgentResultFailure(error=ErrorArtifact(e).to_dict(), result_details=err_msg)

    def on_handle_configure_agent_request(self, request: ConfigureAgentRequest) -> ResultPayload:
        try:
            if self.prompt_driver is None:
                self.prompt_driver = self._initialize_prompt_driver()
            for key, value in request.prompt_driver.items():
                setattr(self.prompt_driver, key, value)

            if self.image_tool is None:
                self.image_tool = self._initialize_image_tool()
            for key, value in request.image_generation_driver.items():
                setattr(self.image_tool.image_generation_driver, key, value)
        except Exception as e:
            details = f"Error configuring agent: {e}"
            logger.error(details)
            return ConfigureAgentResultFailure(result_details=details)
        return ConfigureAgentResultSuccess(result_details="Agent configured successfully.")

    def on_handle_get_conversation_memory_request(self, request: GetConversationMemoryRequest) -> ResultPayload:
        try:
            thread_id = request.thread_id

            driver = self.thread_storage_driver.get_conversation_memory_driver(thread_id)
            conversation_memory = ConversationMemory(conversation_memory_driver=driver)
            runs = conversation_memory.runs

        except Exception as e:
            details = f"Error getting conversation memory: {e}"
            logger.error(details)
            return GetConversationMemoryResultFailure(result_details=details)

        return GetConversationMemoryResultSuccess(
            runs=runs, thread_id=thread_id, result_details="Conversation memory retrieved successfully."
        )

    def on_handle_create_thread_request(self, request: CreateThreadRequest) -> ResultPayload:
        try:
            thread_id, meta = self.thread_storage_driver.create_thread(title=request.title, local_id=request.local_id)

            return CreateThreadResultSuccess(
                thread_id=thread_id,
                title=meta.get("title"),
                created_at=meta["created_at"],
                updated_at=meta["updated_at"],
                result_details="Thread created successfully.",
            )
        except Exception as e:
            details = f"Error creating thread: {e}"
            logger.error(details)
            return CreateThreadResultFailure(result_details=details)

    def on_handle_list_threads_request(self, _: ListThreadsRequest) -> ResultPayload:
        try:
            threads = self.thread_storage_driver.list_threads()
            return ListThreadsResultSuccess(threads=threads, result_details="Threads retrieved successfully.")
        except Exception as e:
            details = f"Error listing threads: {e}"
            logger.error(details)
            return ListThreadsResultFailure(result_details=details)

    def on_handle_delete_thread_request(self, request: DeleteThreadRequest) -> ResultPayload:
        try:
            self.thread_storage_driver.delete_thread(request.thread_id)
            return DeleteThreadResultSuccess(thread_id=request.thread_id, result_details="Thread deleted successfully.")
        except ValueError as e:
            details = str(e)
            logger.error(details)
            return DeleteThreadResultFailure(result_details=details)
        except Exception as e:
            details = f"Error deleting thread: {e}"
            logger.error(details)
            return DeleteThreadResultFailure(result_details=details)

    def on_handle_rename_thread_request(self, request: RenameThreadRequest) -> ResultPayload:
        try:
            if not self.thread_storage_driver.thread_exists(request.thread_id):
                details = f"Thread {request.thread_id} not found"
                logger.error(details)
                return RenameThreadResultFailure(result_details=details)

            updated_meta = self.thread_storage_driver.update_thread_metadata(request.thread_id, title=request.new_title)

            return RenameThreadResultSuccess(
                thread_id=request.thread_id,
                title=updated_meta["title"],
                updated_at=updated_meta["updated_at"],
                result_details="Thread renamed successfully.",
            )
        except Exception as e:
            details = f"Error renaming thread: {e}"
            logger.error(details)
            return RenameThreadResultFailure(result_details=details)

    def on_handle_archive_thread_request(self, request: ArchiveThreadRequest) -> ResultPayload:
        try:
            if not self.thread_storage_driver.thread_exists(request.thread_id):
                details = f"Thread {request.thread_id} not found"
                logger.error(details)
                return ArchiveThreadResultFailure(result_details=details)

            meta = self.thread_storage_driver.get_thread_metadata(request.thread_id)
            if meta.get("archived", False):
                details = f"Thread {request.thread_id} is already archived"
                logger.error(details)
                return ArchiveThreadResultFailure(result_details=details)

            updated_meta = self.thread_storage_driver.update_thread_metadata(request.thread_id, archived=True)

            return ArchiveThreadResultSuccess(
                thread_id=request.thread_id,
                updated_at=updated_meta["updated_at"],
                result_details="Thread archived successfully.",
            )
        except Exception as e:
            details = f"Error archiving thread: {e}"
            logger.error(details)
            return ArchiveThreadResultFailure(result_details=details)

    def on_handle_unarchive_thread_request(self, request: UnarchiveThreadRequest) -> ResultPayload:
        try:
            if not self.thread_storage_driver.thread_exists(request.thread_id):
                details = f"Thread {request.thread_id} not found"
                logger.error(details)
                return UnarchiveThreadResultFailure(result_details=details)

            meta = self.thread_storage_driver.get_thread_metadata(request.thread_id)
            if not meta.get("archived", False):
                details = f"Thread {request.thread_id} is not archived"
                logger.error(details)
                return UnarchiveThreadResultFailure(result_details=details)

            updated_meta = self.thread_storage_driver.update_thread_metadata(request.thread_id, archived=False)

            return UnarchiveThreadResultSuccess(
                thread_id=request.thread_id,
                updated_at=updated_meta["updated_at"],
                result_details="Thread unarchived successfully.",
            )
        except Exception as e:
            details = f"Error unarchiving thread: {e}"
            logger.error(details)
            return UnarchiveThreadResultFailure(result_details=details)

    def on_handle_list_available_models_request(self, _request: ListAvailableModelsRequest) -> ResultPayload:
        """Handle request to list available prompt and image models from Griptape Cloud."""
        try:
            # Fetch models from Griptape Cloud API
            api_key = secrets_manager.get_secret(API_KEY_ENV_VAR)
            if not api_key:
                details = f"Secret '{API_KEY_ENV_VAR}' not found"
                return ListAvailableModelsResultFailure(result_details=details)

            headers = {"Authorization": f"Bearer {api_key}"}

            # Fetch prompt/chat models
            prompt_response = requests.get(CHAT_MODELS_URL, headers=headers, timeout=10)
            prompt_response.raise_for_status()
            prompt_data = prompt_response.json()["models"]
            prompt_models = [model["model_name"] for model in prompt_data]
            default_prompt_model = next(filter(lambda x: x["default"], prompt_data))["model_name"]

            # Fetch image generation models
            image_response = requests.get(IMAGE_MODELS_URL, headers=headers, timeout=10)
            image_response.raise_for_status()
            image_data = image_response.json()["models"]
            image_models = [model["model_name"] for model in image_data]
            default_image_model = next(filter(lambda x: x["default"], image_data))["model_name"]

            return ListAvailableModelsResultSuccess(
                prompt_models=prompt_models,
                image_models=image_models,
                default_prompt_model=default_prompt_model,
                default_image_model=default_image_model,
                result_details="Successfully retrieved available models from Griptape Cloud.",
            )
        except Exception as e:
            details = f"Error listing available models: {e}"
            logger.error(details)
            return ListAvailableModelsResultFailure(result_details=details)

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        secrets_manager = GriptapeNodes.SecretsManager()
        api_key = secrets_manager.get_secret("GT_CLOUD_API_KEY")
        # Start MCP server in daemon thread
        threading.Thread(target=start_mcp_server, args=(api_key,), daemon=True, name="mcp-server").start()

    def _on_handle_run_agent_request(self, request: RunAgentRequest) -> ResultPayload:
        # EventBus functionality removed - events now go directly to event queue
        try:
            # Get or create thread and validate
            try:
                thread_id = self._validate_thread_for_run(request.thread_id)
            except ValueError as e:
                details = str(e)
                return RunAgentResultFailure(error={"message": details}, result_details=details)

            # Check if this is the first run
            driver = self.thread_storage_driver.get_conversation_memory_driver(thread_id)
            conversation_memory = ConversationMemory(conversation_memory_driver=driver)
            is_first_run = len(conversation_memory.runs) == 0

            artifacts = [
                ImageLoader().parse(ImageUrlArtifact.from_dict(url_artifact).to_bytes())
                for url_artifact in request.url_artifacts
                if url_artifact["type"] == "ImageUrlArtifact"
            ]
            # Log prompt driver configuration BEFORE creating agent
            if self.prompt_driver:
                logger.info("AgentManager prompt_driver model: %s", self.prompt_driver.model)
                logger.info(
                    "AgentManager prompt_driver structured_output_strategy: %s",
                    getattr(self.prompt_driver, "structured_output_strategy", "NOT SET"),
                )
                logger.info("AgentManager prompt_driver stream: %s", self.prompt_driver.stream)

            agent = self._create_agent(thread_id=thread_id, additional_mcp_servers=request.additional_mcp_servers)

            # Log agent configuration after creation
            logger.info("Agent output_schema type: %s", type(agent.output_schema))
            logger.info("Agent output_schema: %s", agent.output_schema)

            event_stream = agent.run_stream([request.input, *artifacts])
            self._process_agent_stream(event_stream)

            if isinstance(agent.output, ErrorArtifact):
                return RunAgentResultFailure(error=agent.output.to_dict(), result_details=agent.output.to_json())

            # Auto-generate title from first message if needed
            if is_first_run:
                title = self._generate_title_from_input(request.input)
                self.thread_storage_driver.update_thread_metadata(thread_id, title=title)
            else:
                # Just update the timestamp
                self.thread_storage_driver.update_thread_metadata(thread_id)

            return RunAgentResultSuccess(
                output=agent.output.to_dict(),
                thread_id=thread_id,
                result_details="Agent execution completed successfully.",
            )
        except Exception as e:
            err_msg = f"Error running agent: {e}"
            logger.exception(err_msg)
            return RunAgentResultFailure(error=ErrorArtifact(e).to_dict(), result_details=err_msg)

    def _create_agent(self, thread_id: str, additional_mcp_servers: list[str] | None = None) -> Agent:
        output_schema = create_model(
            "AgentOutputSchema",
            conversation_output=(str, ...),
            generated_image_urls=(list[str], ...),
        )

        tools = []
        if self.image_tool is not None:
            tools.append(self.image_tool)
        if self.mcp_tool is not None:
            tools.append(self.mcp_tool)

        # Add additional MCP servers if specified
        if additional_mcp_servers:
            additional_tools = self._create_additional_mcp_tools(additional_mcp_servers)
            tools.extend(additional_tools)

        # Get thread-specific conversation memory
        driver = self.thread_storage_driver.get_conversation_memory_driver(thread_id)
        conversation_memory = ConversationMemory(conversation_memory_driver=driver)

        # Collect MCP server rulesets
        mcp_rulesets = self._collect_mcp_server_rulesets(additional_mcp_servers)

        # Get default rulesets
        default_rulesets = self._get_default_rulesets()

        return Agent(
            prompt_driver=self.prompt_driver,
            conversation_memory=conversation_memory,
            tools=tools,
            output_schema=output_schema,
            rulesets=[*default_rulesets, *mcp_rulesets],
        )

    @staticmethod
    def _create_ruleset_from_rules_string(rules_string: str | None, server_name: str) -> Ruleset | None:
        """Create a Ruleset from a rules string for an MCP server.

        Args:
            rules_string: Optional rules string for the MCP server
            server_name: Name of the MCP server

        Returns:
            Ruleset with a single Rule containing the rules string, or None if rules_string is None/empty
        """
        if not rules_string or not rules_string.strip():
            return None

        rules_text = rules_string.strip()
        ruleset_name = f"mcp_{server_name}_rules"

        return Ruleset(name=ruleset_name, rules=[Rule(rules_text)])

    def _collect_mcp_server_rulesets(self, additional_mcp_servers: list[str] | None) -> list[Ruleset]:
        """Collect rulesets from MCP server configurations."""
        mcp_rulesets = []

        # Collect server names to get rules for
        server_names_to_check = []
        if additional_mcp_servers:
            server_names_to_check.extend(additional_mcp_servers)

        # Get rules for all MCP servers
        if not server_names_to_check:
            return mcp_rulesets

        enabled_result = GriptapeNodes.handle_request(GetEnabledMCPServersRequest())
        if not isinstance(enabled_result, GetEnabledMCPServersResultSuccess):
            return mcp_rulesets

        for server_name in server_names_to_check:
            if server_name not in enabled_result.servers:
                continue

            server_config = enabled_result.servers[server_name]
            rules_string = server_config.get("rules")
            ruleset = AgentManager._create_ruleset_from_rules_string(rules_string, server_name)
            if ruleset is not None:
                mcp_rulesets.append(ruleset)

        return mcp_rulesets

    def _get_default_rulesets(self) -> list[Ruleset]:
        """Get the default rulesets for agents."""
        return [
            Ruleset(
                name="generated_image_urls",
                rules=[
                    Rule("Do not hallucinate generated_image_urls."),
                    Rule("Only set generated_image_urls with images generated with your tools."),
                ],
            ),
            # Note: Griptape's MCPTool automatically wraps arguments in a 'values' key, but our MCP server
            # expects arguments directly. This ruleset instructs the agent to provide arguments without
            # the 'values' wrapper to avoid validation errors. If MCPTool behavior changes in the future,
            # this ruleset may need to be updated or removed.
            Ruleset(
                name="mcp_tool_usage",
                rules=[
                    Rule(
                        "When calling MCP tools (mcpGriptapeNodes), provide arguments directly without wrapping them in a 'values' key. "
                        "For example, use {'node_type': 'FluxImageGeneration', 'node_name': 'MyNode'} not {'values': {'node_type': 'FluxImageGeneration'}}."
                    ),
                ],
            ),
            Ruleset(
                name="node_rulesets",
                rules=[
                    Rule(
                        "When asked to create a node, use ListNodeTypesInLibraryRequest or GetAllInfoForAllLibrariesRequest to check available node types and find the appropriate node."
                    ),
                    Rule(
                        "When matching user requests to node types, account for variations: users may include spaces (e.g., 'Image Generation' vs 'ImageGeneration') or reorder words (e.g., 'Generate Image' vs 'Image Generation'). Match based on the words present, not exact spelling."
                    ),
                    Rule(
                        "If you cannot determine the correct node type or node creation fails, ask the user for clarification."
                    ),
                ],
            ),
        ]

    def _validate_thread_for_run(self, thread_id: str | None) -> str:
        """Validate and return thread_id for agent run, or raise ValueError."""
        if thread_id is None:
            thread_id, _ = self.thread_storage_driver.create_thread()
            return thread_id

        meta = self.thread_storage_driver.get_thread_metadata(thread_id)
        if meta.get("archived", False):
            details = f"Cannot run agent on archived thread {thread_id}. Unarchive it first."
            logger.error(details)
            raise ValueError(details)

        return thread_id

    def _process_agent_stream(self, event_stream: Iterator) -> None:
        """Process agent stream events and emit streaming tokens."""
        full_result = ""
        last_conversation_output = ""
        for event in event_stream:
            if isinstance(event, TextChunkEvent):
                full_result += event.token
                try:
                    result_json = json.loads(repair_json(full_result))

                    if isinstance(result_json, dict) and "conversation_output" in result_json:
                        new_conversation_output = result_json["conversation_output"]
                        if new_conversation_output != last_conversation_output:
                            GriptapeNodes.EventManager().put_event(
                                ExecutionGriptapeNodeEvent(
                                    wrapped_event=ExecutionEvent(
                                        payload=AgentStreamEvent(
                                            token=new_conversation_output[len(last_conversation_output) :]
                                        )
                                    )
                                )
                            )
                            last_conversation_output = new_conversation_output
                except json.JSONDecodeError:
                    pass  # Ignore incomplete JSON

    def _initialize_prompt_driver(self) -> GriptapeCloudPromptDriver:
        api_key = secrets_manager.get_secret(API_KEY_ENV_VAR)
        if not api_key:
            msg = f"Secret '{API_KEY_ENV_VAR}' not found"
            raise ValueError(msg)
        return GriptapeCloudPromptDriver(api_key=api_key, stream=True)

    def _initialize_image_tool(self) -> NodesPromptImageGenerationTool:
        api_key = secrets_manager.get_secret(API_KEY_ENV_VAR)
        if not api_key:
            msg = f"Secret '{API_KEY_ENV_VAR}' not found"
            raise ValueError(msg)
        return NodesPromptImageGenerationTool(
            image_generation_driver=GriptapeCloudImageGenerationDriver(api_key=api_key),
            static_files_manager=self.static_files_manager,
        )

    def _initialize_mcp_tool(self) -> MCPTool:
        connection: StreamableHttpConnection = {  # type: ignore[reportAssignmentType]
            "transport": "streamable_http",
            "url": f"http://localhost:{GTN_MCP_SERVER_PORT}/mcp/",
        }
        return MCPTool(connection=connection, name="mcpGriptapeNodes")

    def _initialize_thread_storage_driver(self) -> LocalThreadStorageDriver | GriptapeCloudThreadStorageDriver:
        """Initialize the appropriate thread storage driver based on configuration."""
        storage_backend = config_manager.get_config_value("thread_storage_backend")

        if storage_backend == "gtc":
            return GriptapeCloudThreadStorageDriver(config_manager, secrets_manager)

        return LocalThreadStorageDriver(self._threads_dir, config_manager, secrets_manager)

    def _create_additional_mcp_tools(self, server_names: list[str]) -> list[MCPTool]:
        """Create MCP tools for additional servers specified in the request."""
        additional_tools = []

        try:
            enabled_result = GriptapeNodes.handle_request(GetEnabledMCPServersRequest())

            if not isinstance(enabled_result, GetEnabledMCPServersResultSuccess):
                msg = f"Failed to get enabled MCP servers for additional tools: {enabled_result}. Agent will continue with default MCP tool only."
                logger.warning(msg)
                return additional_tools

            for server_name in server_names:
                if server_name in enabled_result.servers:
                    server_config = enabled_result.servers[server_name]
                    connection = self._create_connection_from_mcp_config(server_config)  # type: ignore[arg-type]
                    tool = MCPTool(connection=connection, name=f"mcp{server_name.title()}")  # type: ignore[arg-type]
                    additional_tools.append(tool)
                else:
                    msg = f"Additional MCP server '{server_name}' not found or not enabled"
                    logger.warning(msg)

        except Exception as e:
            msg = f"Failed to create additional MCP tools: {e}"
            logger.error(msg)

        return additional_tools

    def _create_connection_from_mcp_config(self, server_config: dict) -> dict:
        """Create connection dictionary from MCP server configuration."""
        transport = server_config.get("transport", "stdio")

        # Start with transport
        connection = {"transport": transport}

        # Map relevant fields based on transport type
        fields_to_map = self.TRANSPORT_FIELD_MAPPINGS.get(transport, self.TRANSPORT_FIELD_MAPPINGS["stdio"])
        for field_name in fields_to_map:
            if field_name in server_config and server_config[field_name] is not None:
                connection[field_name] = server_config[field_name]

        return connection

    def _generate_title_from_input(self, user_input: str, max_length: int = 50) -> str:
        """Generate a thread title from user input."""
        if len(user_input) <= max_length:
            return user_input

        return user_input[:max_length].rsplit(" ", 1)[0] + "..."
