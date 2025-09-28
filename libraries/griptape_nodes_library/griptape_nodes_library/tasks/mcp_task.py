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

        # Get available MCP servers for the dropdown
        mcp_servers = self._get_available_mcp_servers()

        self.add_parameter(
            Parameter(
                name="mcp_server_id",
                input_types=["str"],
                type="str",
                default_value=None,
                tooltip="Select an MCP server to use",
                traits={
                    Options(choices=mcp_servers),
                    Button(
                        full_width=True,
                        label="Refresh MCP Servers",
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
        self.add_parameter(
            Parameter(
                name="output",
                input_types=["str"],
                type="str",
                default_value=None,
                tooltip="The output of the task",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Input text to process"},
            )
        )

        # Add status parameters using the helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the MCP task execution result",
            result_details_placeholder="Details on the MCP task execution will be presented here.",
            parameter_group_initially_collapsed=False,
        )

    def _get_available_mcp_servers(self) -> list[str]:
        """Get list of available MCP server IDs for the dropdown."""
        try:
            app = GriptapeNodes()
            mcp_manager = app.MCPManager()

            # Get enabled MCP servers
            enabled_request = GetEnabledMCPServersRequest()
            enabled_result = mcp_manager.on_get_enabled_mcp_servers_request(enabled_request)

            if hasattr(enabled_result, "servers"):
                return list(enabled_result.servers.keys())
            return []
        except Exception as e:
            logger.warning(f"Failed to get MCP servers: {e}")
            return []

    def _reload_mcp_servers(self, button: Button, button_details: ButtonDetailsMessagePayload) -> None:  # noqa: ARG002
        """Reload MCP servers when the refresh button is clicked."""
        try:
            # Get fresh list of MCP servers
            mcp_servers = self._get_available_mcp_servers()

            # Update the parameter's choices using the proper method
            if mcp_servers:
                # Use _update_option_choices to properly update both trait and UI options
                self._update_option_choices("mcp_server_id", mcp_servers, mcp_servers[0])
                logger.info(f"Refreshed MCP servers: {len(mcp_servers)} servers available")
            else:
                # No servers available - use proper method
                self._update_option_choices("mcp_server_id", ["No MCP servers available"], "No MCP servers available")
                logger.info("No MCP servers available")

        except Exception as e:
            logger.error(f"Failed to reload MCP servers: {e}")

    async def aprocess(self) -> None:
        # Reset execution state and set failure defaults
        self._clear_execution_status()
        self._set_failure_output_values()

        # Get parameter values
        mcp_server_id = self.get_parameter_value("mcp_server_id")
        prompt = self.get_parameter_value("prompt")
        off_prompt = self.parameter_values.get("off_prompt", False)
        agent = None
        prev_tools = None

        # self.agent_input = self.get_parameter_value("agent")

        # Validation failures - early returns
        if not mcp_server_id:
            error_details = "No MCP server selected. Please select an MCP server from the dropdown."
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"MCPTaskNode '{self.name}': {error_details}")
            self._handle_failure_exception(ValueError(error_details))
            return

        if not prompt:
            error_details = "No prompt provided. Please enter a prompt to process."
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"MCPTaskNode '{self.name}': {error_details}")
            self._handle_failure_exception(ValueError(error_details))
            return

        # MCP server validation
        try:
            app = GriptapeNodes()
            mcp_manager = app.MCPManager()

            # Get enabled MCP servers
            enabled_request = GetEnabledMCPServersRequest()
            enabled_result = mcp_manager.on_get_enabled_mcp_servers_request(enabled_request)

            if not hasattr(enabled_result, "servers") or mcp_server_id not in enabled_result.servers:
                error_details = f"MCP server '{mcp_server_id}' not found or not enabled."
                self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
                logger.error(f"MCPTaskNode '{self.name}': {error_details}")
                self._handle_failure_exception(ValueError(error_details))
                return

            server_config = enabled_result.servers[mcp_server_id]
        except Exception as mcp_error:
            error_details = f"Failed to get MCP server configuration: {mcp_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"MCPTaskNode '{self.name}': {error_details}")
            self._handle_failure_exception(mcp_error)
            return

        # MCP tool creation and execution
        try:
            # Create MCP connection from server config
            connection: dict[str, Any] = {  # type: ignore[reportAssignmentType]
                "transport": "stdio",
                "command": server_config["command"],
                "args": server_config["args"],
                "env": server_config.get("env", {}),
            }

            # Create the tool
            tool = MCPTool(connection=connection, off_prompt=off_prompt)  # type: ignore[arg-type]

            # Initialize the tool activities
            await tool._init_activities()

            rulesets = []
            tools = []
            agent = self.get_parameter_value("agent")
            if isinstance(agent, dict):
                # The agent is conected. We'll use that
                agent = Agent().from_dict(agent)
                task = agent.tasks[0]
                driver = task.prompt_driver
                tools = task.tools
            else:
                driver = self._create_driver()
                agent = Agent()

            prompt_task = PromptTask(tools=[*tools, tool], prompt_driver=driver, rulesets=rulesets)
            agent.add_task(prompt_task)

            # Run the process with proper streaming
            result = self._process_with_streaming(agent, prompt)

            # Success path
            self._set_success_output_values(prompt, result)
            success_details = f"Successfully executed MCP task with server '{mcp_server_id}'"
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

    def _set_failure_output_values(self) -> None:
        """Set output parameter values to defaults on failure."""
        self.parameter_output_values["prompt"] = ""
        self.parameter_output_values["output"] = ""
        # self.parameter_output_values["agent"] = None
