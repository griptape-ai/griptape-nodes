import time
from typing import Any

from griptape.artifacts import BaseArtifact
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.events import ActionChunkEvent, FinishStructureRunEvent, StartStructureRunEvent, TextChunkEvent
from griptape.structures import Agent
from griptape.tasks import PromptTask
from griptape.tools import MCPTool

from griptape_nodes.exe_types.core_types import Parameter, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, SuccessFailureNode
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.mcp_utils import (
    create_mcp_tool,
    get_available_mcp_servers,
    get_server_config,
    validate_mcp_server,
)


class MCPTaskNode(SuccessFailureNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Cache MCP tools to avoid expensive re-initialization
        # MCPTool creation + _init_activities() takes ~1-2 seconds per tool
        # This cache persists for the lifetime of this node instance
        self._mcp_tools: dict[str, MCPTool] = {}

        # Get available MCP servers for the dropdown
        mcp_servers = get_available_mcp_servers()
        default_mcp_server = mcp_servers[0] if mcp_servers else None
        self.add_parameter(
            ParameterString(
                name="mcp_server_name",
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
                placeholder_text="Select MCP server...",
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
            ParameterInt(
                name="max_subtasks",
                default_value=20,
                hide=True,
                tooltip="The maximum number of subtasks to allow.",
                min_val=1,
                max_val=100,
            )
        )
        self.add_parameter(
            ParameterString(
                name="prompt",
                default_value=None,
                tooltip="The prompt to use",
                multiline=True,
                placeholder_text="Input text to process",
            )
        )
        self.add_parameter(
            ParameterList(
                name="context",
                tooltip="Additional context to add to the prompt",
                input_types=["Any"],
                allowed_modes={ParameterMode.INPUT},
            )
        )
        self.output = ParameterString(
            name="output",
            default_value=None,
            tooltip="The output of the task",
            allowed_modes={ParameterMode.OUTPUT},
            multiline=True,
            markdown=True,
            placeholder_text="The results of the MCP task will be displayed here.",
        )
        self.add_parameter(self.output)

        # Add status parameters using the helper method
        self._create_status_parameters(
            result_details_tooltip="Details about the MCP task execution result",
            result_details_placeholder="Details on the MCP task execution will be presented here.",
            parameter_group_initially_collapsed=False,
        )

    def _reload_mcp_servers(self, button: Button, button_details: ButtonDetailsMessagePayload) -> None:  # noqa: ARG002
        """Reload MCP servers when the refresh button is clicked."""
        try:
            # Get fresh list of MCP servers
            mcp_servers = get_available_mcp_servers()

            # Update the parameter's choices using the proper method
            if mcp_servers:
                current_value = self.get_parameter_value("mcp_server_name")
                if current_value in mcp_servers:
                    default_value = current_value
                else:
                    default_value = mcp_servers[0]

                # Use _update_option_choices to properly update both trait and UI options
                self._update_option_choices("mcp_server_name", mcp_servers, default_value)
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

        # Validate prompt
        if not prompt:
            msg = f"{self.name}: No prompt provided. Please enter a prompt to process."
            exceptions.append(ValueError(msg))

        # Validate MCP server exists and is enabled
        if mcp_server_name:
            is_valid, error_msg = validate_mcp_server(mcp_server_name)
            if not is_valid:
                msg = f"{self.name}: {error_msg}"
                exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def _get_or_create_mcp_tool(self, mcp_server_name: str, server_config: dict[str, Any] | str) -> MCPTool:
        """Get or create MCP tool, caching it to avoid expensive re-initialization.

        MCPTool creation involves establishing connections to MCP servers and discovering
        their capabilities, which can take 1-2 seconds per tool. Caching prevents this
        overhead on subsequent runs within the same node instance.
        """
        if mcp_server_name not in self._mcp_tools:
            # Create MCP tool using utility function
            tool = create_mcp_tool(mcp_server_name, server_config)  # type: ignore[arg-type]

            # Cache the initialized tool for future use
            self._mcp_tools[mcp_server_name] = tool
        else:
            # Tool already exists in cache - reuse it to avoid expensive re-initialization
            logger.debug(f"MCPTaskNode '{self.name}': Using cached MCP tool for '{mcp_server_name}'")

        return self._mcp_tools[mcp_server_name]

    def process(self) -> AsyncResult:
        # Reset execution state and set failure defaults
        self._clear_execution_status()
        self._set_failure_output_values()
        self.publish_update_to_parameter("output", "")

        # Get parameter values
        mcp_server_name = self.get_parameter_value("mcp_server_name")
        prompt = self.get_parameter_value("prompt")
        max_subtasks = self.get_parameter_value("max_subtasks")
        context = self.get_parameter_list_value("context")

        # add any context to the prompt
        if context:
            prompt += f"\n{context!s}"

        # Get MCP server configuration
        server_config = get_server_config(mcp_server_name)
        if server_config is None:
            error_details = f"MCP server '{mcp_server_name}' not found or not enabled"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"{self.name}: {error_details}")
            return

        # Get MCP tool
        tool = yield lambda: self._get_mcp_tool(mcp_server_name, server_config)
        if tool is None:
            error_details = f"Failed to create MCP tool for server '{mcp_server_name}'"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"{self.name}: {error_details}")
            return

        # Setup agent and task
        agent, driver, tools, rulesets = self._setup_agent()
        if agent is None:
            error_details = "Failed to setup agent"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"{self.name}: {error_details}")
            return

        # Add task to agent
        if not self._add_task_to_agent(agent, tool, driver, tools, rulesets, max_subtasks):
            error_details = "Failed to add task to agent"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"{self.name}: {error_details}")
            return

        # Execute with streaming
        yield lambda: self._execute_with_streaming(agent, prompt, mcp_server_name)

    def _get_mcp_tool(self, mcp_server_name: str, server_config: dict[str, Any]) -> MCPTool | None:
        """Get or create MCP tool."""
        try:
            return self._get_or_create_mcp_tool(mcp_server_name, server_config)
        except Exception as e:
            msg = f"{self.name}: Failed to get or create MCP tool: {e}"
            logger.error(f"MCPTaskNode '{self.name}': {msg}")
            self._handle_failure_exception(e)
            return None

    def _setup_agent(self) -> tuple[Agent | None, Any, list, list]:
        """Setup agent, driver, tools, and rulesets."""
        try:
            rulesets = []
            tools = []
            agent = self.get_parameter_value("agent")
            if isinstance(agent, dict):
                agent = Agent().from_dict(agent)
                task = agent.tasks[0]
                driver = task.prompt_driver
                tools = task.tools
                rulesets = task.rulesets
            else:
                driver = self._create_driver()
                agent = Agent()
        except Exception as e:
            msg = f"{self.name}: Failed to get or create agent: {e}"
            logger.error(f"MCPTaskNode '{self.name}': {msg}")
            self._handle_failure_exception(e)
            return None, None, [], []
        return agent, driver, tools, rulesets

    def _add_task_to_agent(  # noqa: PLR0913
        self, agent: Agent, tool: MCPTool, driver: Any, tools: list, rulesets: list, max_subtasks: int
    ) -> bool:
        """Add task to agent."""
        try:
            prompt_task = PromptTask(
                tools=[*tools, tool], prompt_driver=driver, rulesets=rulesets, max_subtasks=max_subtasks
            )
            agent.add_task(prompt_task)
        except Exception as e:
            msg = f"{self.name}: Failed to add task to agent: {e}"
            logger.error(f"MCPTaskNode '{self.name}': {msg}")
            self._handle_failure_exception(e)
            return False
        return True

    def _execute_with_streaming(self, agent: Agent, prompt: str, mcp_server_name: str) -> None:
        """Execute agent with streaming."""
        try:
            execution_start = time.time()
            logger.debug(f"MCPTaskNode '{self.name}': Starting agent execution with MCP tool...")
            result = self._process_with_streaming(agent, prompt)
            execution_time = time.time() - execution_start
            logger.debug(f"MCPTaskNode '{self.name}': Agent execution completed in {execution_time:.2f}s")

            self._set_success_output_values(result)
            success_details = f"Successfully executed MCP task with server '{mcp_server_name}'"
            self._set_status_results(was_successful=True, result_details=f"SUCCESS: {success_details}")
            logger.info(f"MCPTaskNode '{self.name}': {success_details}")

        except Exception as execution_error:
            error_details = f"MCP task execution failed: {execution_error}"
            self._set_status_results(was_successful=False, result_details=f"FAILURE: {error_details}")
            logger.error(f"MCPTaskNode '{self.name}': {error_details}")
            self._handle_failure_exception(execution_error)

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
            model=model,
            api_key=GriptapeNodes.SecretsManager().get_secret("GT_CLOUD_API_KEY"),
            stream=True,
        )

    def _set_success_output_values(self, result: Agent) -> None:
        """Set output parameter values on success."""
        self.parameter_output_values["output"] = str(result.output) if result.output else ""
        # Remove the MCP Tool from the agent
        if isinstance(result.tasks[0], PromptTask) and result.tasks[0].tools:
            # Filter out MCPTool instances, keep other tools
            result.tasks[0].tools = [tool for tool in result.tasks[0].tools if not isinstance(tool, MCPTool)]

        self.parameter_output_values["agent"] = result.to_dict()

    def _set_failure_output_values(self) -> None:
        """Set output parameter values to defaults on failure."""
        self.parameter_output_values["output"] = ""
