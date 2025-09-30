import asyncio
import json
import logging
import os
import threading
import uuid
from typing import TYPE_CHECKING, ClassVar

from attrs import define, field
from griptape.artifacts import ErrorArtifact, ImageUrlArtifact, JsonArtifact
from griptape.drivers.image_generation import BaseImageGenerationDriver
from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.events import FinishTaskEvent, TextChunkEvent
from griptape.loaders import ImageLoader
from griptape.memory.structure import ConversationMemory
from griptape.rules import Rule, Ruleset
from griptape.structures import Agent
from griptape.tools import BaseImageGenerationTool
from griptape.tools.mcp.tool import MCPTool
from griptape.utils.decorators import activity
from json_repair import repair_json
from schema import Literal, Schema

from griptape_nodes.retained_mode.events.agent_events import (
    AgentStreamEvent,
    ConfigureAgentRequest,
    ConfigureAgentResultFailure,
    ConfigureAgentResultSuccess,
    GetConversationMemoryRequest,
    GetConversationMemoryResultFailure,
    GetConversationMemoryResultSuccess,
    ResetAgentConversationMemoryRequest,
    ResetAgentConversationMemoryResultFailure,
    ResetAgentConversationMemoryResultSuccess,
    RunAgentRequest,
    RunAgentResultFailure,
    RunAgentResultStarted,
    RunAgentResultSuccess,
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
        self.conversation_memory = ConversationMemory()
        self.prompt_driver = None
        self.image_tool = None
        self.mcp_tool = None
        self.static_files_manager = static_files_manager

        if event_manager is not None:
            event_manager.assign_manager_to_request_type(RunAgentRequest, self.on_handle_run_agent_request)
            event_manager.assign_manager_to_request_type(ConfigureAgentRequest, self.on_handle_configure_agent_request)
            event_manager.assign_manager_to_request_type(
                ResetAgentConversationMemoryRequest, self.on_handle_reset_agent_conversation_memory_request
            )
            event_manager.assign_manager_to_request_type(
                GetConversationMemoryRequest, self.on_handle_get_conversation_memory_request
            )
            event_manager.add_listener_to_app_event(
                AppInitializationComplete,
                self.on_app_initialization_complete,
            )
            # TODO: Listen for shutdown event (https://github.com/griptape-ai/griptape-nodes/issues/2149) to stop mcp server

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
            image_generation_driver=GriptapeCloudImageGenerationDriver(api_key=api_key, model="gpt-image-1"),
            static_files_manager=self.static_files_manager,
        )

    def _initialize_mcp_tool(self) -> MCPTool:
        connection: StreamableHttpConnection = {  # type: ignore[reportAssignmentType]
            "transport": "streamable_http",
            "url": f"http://localhost:{GTN_MCP_SERVER_PORT}/mcp/",
        }
        return MCPTool(connection=connection, name="mcpGriptapeNodes")

    def _create_additional_mcp_tools(self, server_names: list[str]) -> list[MCPTool]:
        """Create MCP tools for additional servers specified in the request."""
        additional_tools = []

        try:
            app = GriptapeNodes()

            enabled_request = GetEnabledMCPServersRequest()
            enabled_result = app.handle_request(enabled_request)

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

    async def on_handle_run_agent_request(self, request: RunAgentRequest) -> ResultPayload:
        if self.prompt_driver is None:
            self.prompt_driver = self._initialize_prompt_driver()
        if self.image_tool is None:
            self.image_tool = self._initialize_image_tool()
        if self.mcp_tool is None:
            self.mcp_tool = self._initialize_mcp_tool()
        await asyncio.to_thread(self._on_handle_run_agent_request, request)
        return RunAgentResultStarted(result_details="Agent execution started successfully.")

    def _create_agent(self, additional_mcp_servers: list[str] | None = None) -> Agent:
        output_schema = Schema(
            {
                "generated_image_urls": [str],
                "conversation_output": str,
            }
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

        return Agent(
            prompt_driver=self.prompt_driver,
            conversation_memory=self.conversation_memory,
            tools=tools,
            output_schema=output_schema,
            rulesets=[
                Ruleset(
                    name="generated_image_urls",
                    rules=[
                        Rule("Do not hallucinate generated_image_urls."),
                        Rule("Only set generated_image_urls with images generated with your tools."),
                    ],
                ),
            ],
        )

    def _on_handle_run_agent_request(self, request: RunAgentRequest) -> ResultPayload:
        # EventBus functionality removed - events now go directly to event queue
        try:
            artifacts = [
                ImageLoader().parse(ImageUrlArtifact.from_dict(url_artifact).to_bytes())
                for url_artifact in request.url_artifacts
                if url_artifact["type"] == "ImageUrlArtifact"
            ]
            agent = self._create_agent(additional_mcp_servers=request.additional_mcp_servers)
            *events, last_event = agent.run_stream([request.input, *artifacts])
            full_result = ""
            last_conversation_output = ""
            for event in events:
                if isinstance(event, TextChunkEvent):
                    full_result += event.token
                    try:
                        result_json = json.loads(repair_json(full_result))
                        if "conversation_output" in result_json:
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
            if isinstance(last_event, FinishTaskEvent):
                if isinstance(last_event.task_output, ErrorArtifact):
                    return RunAgentResultFailure(
                        error=last_event.task_output.to_dict(), result_details=last_event.task_output.to_json()
                    )
                if isinstance(last_event.task_output, JsonArtifact):
                    return RunAgentResultSuccess(
                        last_event.task_output.to_dict(), result_details="Agent execution completed successfully."
                    )
            err_msg = f"Unexpected final event: {last_event}"
            logger.error(err_msg)
            return RunAgentResultFailure(error=ErrorArtifact(last_event).to_dict(), result_details=err_msg)
        except Exception as e:
            err_msg = f"Error running agent: {e}"
            logger.error(err_msg)
            return RunAgentResultFailure(error=ErrorArtifact(e).to_dict(), result_details=err_msg)

    def on_handle_configure_agent_request(self, request: ConfigureAgentRequest) -> ResultPayload:
        try:
            if self.prompt_driver is None:
                self.prompt_driver = self._initialize_prompt_driver()
            for key, value in request.prompt_driver.items():
                setattr(self.prompt_driver, key, value)
        except Exception as e:
            details = f"Error configuring agent: {e}"
            logger.error(details)
            return ConfigureAgentResultFailure(result_details=details)
        return ConfigureAgentResultSuccess(result_details="Agent configured successfully.")

    def on_handle_reset_agent_conversation_memory_request(
        self, _: ResetAgentConversationMemoryRequest
    ) -> ResultPayload:
        try:
            self.conversation_memory = ConversationMemory()
        except Exception as e:
            details = f"Error resetting agent conversation memory: {e}"
            logger.error(details)
            return ResetAgentConversationMemoryResultFailure(result_details=details)
        return ResetAgentConversationMemoryResultSuccess(result_details="Agent conversation memory reset successfully.")

    def on_handle_get_conversation_memory_request(self, _: GetConversationMemoryRequest) -> ResultPayload:
        try:
            conversation_memory = self.conversation_memory.runs
        except Exception as e:
            details = f"Error getting conversation memory: {e}"
            logger.error(details)
            return GetConversationMemoryResultFailure(result_details=details)
        return GetConversationMemoryResultSuccess(
            runs=conversation_memory, result_details="Conversation memory retrieved successfully."
        )

    def on_app_initialization_complete(self, _payload: AppInitializationComplete) -> None:
        secrets_manager = GriptapeNodes.SecretsManager()
        api_key = secrets_manager.get_secret("GT_CLOUD_API_KEY")
        # Start MCP server in daemon thread
        threading.Thread(target=start_mcp_server, args=(api_key,), daemon=True, name="mcp-server").start()
