import time
from typing import Any

from griptape.artifacts import BaseArtifact
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.events import ActionChunkEvent, FinishStructureRunEvent, StartStructureRunEvent, TextChunkEvent
from griptape.structures import Agent
from griptape.tasks import PromptTask
from griptape.tools.mcp.tool import MCPTool

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.events.mcp_events import GetEnabledMCPServersRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.options import Options


class MCPTaskNode(SuccessFailureNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Cache MCP tools to avoid expensive re-initialization
        # MCPTool creation + _init_activities() takes ~1-2 seconds per tool
        # This cache persists for the lifetime of this node instance
        self._mcp_tools: dict[str, MCPTool] = {}

        # Get available MCP servers for the dropdown
        mcp_servers = self._get_available_mcp_servers()
        default_mcp_server = mcp_servers[0] if mcp_servers else None
        self.add_parameter(
            Parameter(
                name="mcp_server_name",
                input_types=["str"],
                type="str",
                default_value=default_mcp_server,
                tooltip="Select an MCP server to use",
                traits={
                    Options(choices=mcp_servers),
                    Button(
                        full_width=False,
                        icon="refresh-cw",
                        size="icon",
                        variant="secondary",
                        on_click=self._reload_mcp_servers,
                    ),
                },
                ui_options={"placeholder_text": "Select MCP server..."},
            )
        )
        self.add_parameter(
            Parameter(
                name="agent",
                input_types=["Agent"],
                type="Agent",
                default_value=None,
                tooltip="Optional agent to use - helpful if you want to continue interaction with an existing agent.",
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                default_value=None,
                tooltip="The prompt to use",
                ui_options={"multiline": True, "placeholder_text": "Input text to process"},
            )
        )
        self.output = Parameter(
            name="output",
            input_types=["str"],
            type="str",
            default_value=None,
            tooltip="The output of the task",
            allowed_modes={ParameterMode.OUTPUT},
            ui_options={
                "multiline": True,
                "placeholder_text": "Input text to process",
            },  # TODO: (jason) Make this markdown output to handle images
        )
        self.add_parameter(self.output)

        # Add status parameters using the helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the MCP task execution result",
            result_details_placeholder="Details on the MCP task execution will be presented here.",
            parameter_group_initially_collapsed=False,
        )

    def _get_available_mcp_servers(self) -> list[str]:
        """Get list of available MCP server IDs for the dropdown."""
        servers = []
        try:
            app = GriptapeNodes()
            mcp_manager = app.MCPManager()

            # Get enabled MCP servers
            enabled_request = GetEnabledMCPServersRequest()
            enabled_result = mcp_manager.on_get_enabled_mcp_servers_request(enabled_request)

            if hasattr(enabled_result, "servers"):
                servers.extend(enabled_result.servers.keys())

            # Note: griptape-nodes-local removed from MCPTaskNode due to circular dependency issues
            # It's still available for the agent, but not for MCPTaskNode

        except Exception as e:
            logger.warning(f"Failed to get MCP servers: {e}")
            # Return empty list if no servers available (no griptape-nodes-local for MCPTaskNode)
        return servers

    def _reload_mcp_servers(self, button: Button, button_details: ButtonDetailsMessagePayload) -> None:  # noqa: ARG002
        """Reload MCP servers when the refresh button is clicked."""
        try:
            # Get fresh list of MCP servers
            mcp_servers = self._get_available_mcp_servers()

            # Update the parameter's choices using the proper method
            if mcp_servers:
                # Use _update_option_choices to properly update both trait and UI options
                self._update_option_choices("mcp_server_name", mcp_servers, mcp_servers[0])
                msg = f"{self.name}: Refreshed MCP servers: {len(mcp_servers)} servers available"
                logger.info(f"Refreshed MCP servers: {len(mcp_servers)} servers available")
            else:
                # No servers available - use proper method
                self._update_option_choices("mcp_server_name", ["No MCP servers available"], "No MCP servers available")
                msg = f"{self.name}: No MCP servers available"
                logger.info(msg)

        except Exception as e:
            msg = f"{self.name}: Failed to reload MCP servers: {e}"
            logger.error(msg)

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate node parameters before execution."""
        exceptions = []

        # Get parameter values
        mcp_server_name = self.get_parameter_value("mcp_server_name")
        prompt = self.get_parameter_value("prompt")

        # Validate MCP server selection
        if not mcp_server_name:
            msg = f"{self.name}: No MCP server selected. Please select an MCP server from the dropdown."  # noqa: S608 - false sql injection warning by linter
            exceptions.append(ValueError(msg))

        # Validate prompt
        if not prompt:
            msg = f"{self.name}: No prompt provided. Please enter a prompt to process."
            exceptions.append(ValueError(msg))

        # Validate MCP server exists and is enabled
        if mcp_server_name:
            try:
                app = GriptapeNodes()
                mcp_manager = app.MCPManager()

                # Get enabled MCP servers
                enabled_request = GetEnabledMCPServersRequest()
                enabled_result = mcp_manager.on_get_enabled_mcp_servers_request(enabled_request)

                if not hasattr(enabled_result, "servers") or mcp_server_name not in enabled_result.servers:
                    msg = f"{self.name}: MCP server '{mcp_server_name}' not found or not enabled."
                    exceptions.append(ValueError(msg))
            except Exception as mcp_error:
                msg = f"{self.name}: Failed to get MCP server configuration: {mcp_error}"
                exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    async def _get_or_create_mcp_tool(self, mcp_server_name: str, server_config: dict[str, Any] | str) -> MCPTool:
        """Get or create MCP tool, caching it to avoid expensive re-initialization.

        MCPTool creation involves establishing connections to MCP servers and discovering
        their capabilities, which can take 1-2 seconds per tool. Caching prevents this
        overhead on subsequent runs within the same node instance.
        """
        if mcp_server_name not in self._mcp_tools:
            start_time = time.time()
            logger.info(f"MCPTaskNode '{self.name}': Creating new MCP tool for '{mcp_server_name}'...")

            # Create MCP connection from server config
            connection: dict[str, Any] = self._create_connection_from_config(server_config)  # type: ignore[arg-type]

            # Create tool with unique name
            clean_name = "".join(c for c in mcp_server_name if c.isalnum())
            tool_name = f"mcp{clean_name.title()}"

            # Create and initialize the tool (match agent's parameters exactly)
            tool = MCPTool(connection=connection, name=tool_name)  # type: ignore[arg-type]

            # Initialize tool capabilities - this is the expensive operation we're caching
            init_start = time.time()
            await tool._init_activities()  # Initialize once when created
            init_time = time.time() - init_start

            total_time = time.time() - start_time
            logger.debug(
                f"MCPTaskNode '{self.name}': MCP tool creation took {total_time:.2f}s (init: {init_time:.2f}s)"
            )

            # Cache the initialized tool for future use
            self._mcp_tools[mcp_server_name] = tool
        else:
            # Tool already exists in cache - reuse it to avoid expensive re-initialization
            logger.debug(f"MCPTaskNode '{self.name}': Using cached MCP tool for '{mcp_server_name}'")

        return self._mcp_tools[mcp_server_name]

    async def aprocess(self) -> None:
        # Reset execution state and set failure defaults
        self._clear_execution_status()
        self._set_failure_output_values()
        self.publish_update_to_parameter("output", "")

        # Get parameter values
        mcp_server_name = self.get_parameter_value("mcp_server_name")
        prompt = self.get_parameter_value("prompt")
        agent = None

        # Get MCP server configuration (validation already done in validate_before_node_run)
        try:
            app = GriptapeNodes()
            mcp_manager = app.MCPManager()

            # Get enabled MCP servers
            enabled_request = GetEnabledMCPServersRequest()
            enabled_result = mcp_manager.on_get_enabled_mcp_servers_request(enabled_request)
            server_config = enabled_result.servers[mcp_server_name]
        except Exception as mcp_error:
            error_details = f"Failed to get MCP server configuration: {mcp_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"MCPTaskNode '{self.name}': {error_details}")
            self._handle_failure_exception(mcp_error)
            return

        # MCP tool creation and execution
        try:
            # Get or create cached MCP tool (like the agent does)
            tool = await self._get_or_create_mcp_tool(mcp_server_name, server_config)

            rulesets = []
            tools = []
            agent = self.get_parameter_value("agent")
            if isinstance(agent, dict):
                # The agent is conected. We'll use that
                agent = Agent().from_dict(agent)
                task = agent.tasks[0]
                driver = task.prompt_driver
                tools = task.tools
                rulesets = task.rulesets
            else:
                driver = self._create_driver()
                agent = Agent()

            prompt_task = PromptTask(tools=[*tools, tool], prompt_driver=driver, rulesets=rulesets)
            agent.add_task(prompt_task)

            # Run the process with proper streaming
            execution_start = time.time()
            logger.debug(f"MCPTaskNode '{self.name}': Starting agent execution with MCP tool...")
            result = self._process_with_streaming(agent, prompt)
            execution_time = time.time() - execution_start
            logger.debug(f"MCPTaskNode '{self.name}': Agent execution completed in {execution_time:.2f}s")

            # Success path
            self._set_success_output_values(prompt, result)
            success_details = f"Successfully executed MCP task with server '{mcp_server_name}'"
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
            logger.info(f"MCPTaskNode '{self.name}': {success_details}")

        except Exception as execution_error:
            error_details = f"MCP task execution failed: {execution_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"MCPTaskNode '{self.name}': {error_details}")
            self._handle_failure_exception(execution_error)
            return

    def _process_with_streaming(self, agent: Agent, prompt: BaseArtifact | str) -> Agent:
        """Process the agent with proper streaming, similar to the Agent node."""
        args = [prompt] if prompt else []
        structure_id_stack = []
        active_structure_id = None

        task = agent.tasks[0]
        if not isinstance(task, PromptTask):
            msg = "Agent must have a PromptTask"
            raise TypeError(msg)
        prompt_driver = task.prompt_driver

        if prompt_driver.stream:
            for event in agent.run_stream(
                *args, event_types=[StartStructureRunEvent, TextChunkEvent, ActionChunkEvent, FinishStructureRunEvent]
            ):
                if isinstance(event, StartStructureRunEvent):
                    active_structure_id = event.structure_id
                    structure_id_stack.append(active_structure_id)
                if isinstance(event, FinishStructureRunEvent):
                    structure_id_stack.pop()
                    active_structure_id = structure_id_stack[-1] if structure_id_stack else None

                # Only show events from this agent
                if agent.id == active_structure_id:
                    if isinstance(event, TextChunkEvent):
                        self.append_value_to_parameter("output", value=event.token)
                    if isinstance(event, ActionChunkEvent) and event.name:
                        self.append_value_to_parameter("output", f"\n[Using tool {event.name}]\n")
        else:
            agent.run(*args)
            self.append_value_to_parameter("output", value=str(agent.output))

        return agent

    def _create_driver(self, model: str = "gpt-4.1") -> GriptapeCloudPromptDriver:
        """Create a GriptapeCloudPromptDriver."""
        return GriptapeCloudPromptDriver(
            model=model, api_key=self.get_config_value(service="Griptape", value="GT_CLOUD_API_KEY"), stream=True
        )

    def _set_success_output_values(self, prompt: str, result: Agent) -> None:
        """Set output parameter values on success."""
        self.parameter_output_values["prompt"] = prompt
        self.parameter_output_values["output"] = str(result.output) if result.output else ""
        # Remove the MCP Tool from the agent
        if isinstance(result.tasks[0], PromptTask) and result.tasks[0].tools:
            # Filter out MCPTool instances, keep other tools
            result.tasks[0].tools = [tool for tool in result.tasks[0].tools if not isinstance(tool, MCPTool)]

        self.parameter_output_values["agent"] = result.to_dict()

    def _create_connection_from_config(self, server_config: dict[str, Any]) -> dict[str, Any]:
        """Create a connection dictionary from server configuration based on transport type."""
        transport = server_config.get("transport", "stdio")

        # Define field mappings for each transport type
        field_mappings = {
            "stdio": ["command", "args", "env", "cwd", "encoding", "encoding_error_handler"],
            "sse": ["url", "headers", "timeout", "sse_read_timeout"],
            "streamable_http": ["url", "headers", "timeout", "sse_read_timeout", "terminate_on_close"],
            "websocket": ["url"],
        }

        # Start with transport
        connection = {"transport": transport}

        # Map relevant fields based on transport type
        fields_to_map = field_mappings.get(transport, field_mappings["stdio"])
        for field in fields_to_map:
            if field in server_config and server_config[field] is not None:
                connection[field] = server_config[field]

        return connection

    def _set_failure_output_values(self) -> None:
        """Set output parameter values to defaults on failure."""
        self.parameter_output_values["prompt"] = ""
        self.parameter_output_values["output"] = ""
