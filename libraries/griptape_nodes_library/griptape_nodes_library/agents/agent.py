"""Defines the ExampleAgent node, providing an interface to interact with a Griptape Agent.

This node allows users to create a new Griptape Agent or continue interaction
with an existing one. It defaults to using the Griptape Cloud prompt driver
but supports connecting custom prompt_model_configurations. It handles parameters
for tools, rulesets, prompts, and streams output back to the user interface.
"""

from typing import Any

from griptape.artifacts import BaseArtifact, ModelArtifact
from griptape.drivers.prompt.base_prompt_driver import BasePromptDriver
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.events import ActionChunkEvent, FinishStructureRunEvent, StartStructureRunEvent, TextChunkEvent
from griptape.structures import Structure
from griptape.tasks import PromptTask
from jinja2 import Template
from json_schema_to_pydantic import create_model  # pyright: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode, ParameterType
from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode, ControlNode
from griptape_nodes.retained_mode.events.connection_events import DeleteConnectionRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.agents.griptape_nodes_agent import GriptapeNodesAgent as GtAgent
from griptape_nodes_library.utils.error_utils import try_throw_error

# --- Constants ---
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
MODEL_CHOICES_ARGS = [
    {
        "name": "claude-sonnet-4-20250514",
        "icon": "logos/anthropic.svg",
        "args": {"stream": True, "structured_output_strategy": "tool", "max_tokens": 64000},
    },
    {
        "name": "claude-3-7-sonnet",
        "icon": "logos/anthropic.svg",
        "args": {"stream": True, "structured_output_strategy": "tool", "max_tokens": 64000},
    },
    {
        "name": "deepseek.r1-v1",
        "icon": "logos/deepseek.svg",
        "args": {"stream": False, "structured_output_strategy": "tool", "top_p": None},
    },
    {
        "name": "gemini-2.5-flash-preview-05-20",
        "icon": "logos/google.svg",
        "args": {"stream": True, "structured_output_strategy": "tool"},
    },
    {
        "name": "gemini-2.0-flash",
        "icon": "logos/google.svg",
        "args": {"stream": True, "structured_output_strategy": "tool"},
    },
    {
        "name": "llama3-3-70b-instruct-v1",
        "icon": "logos/meta.svg",
        "args": {"stream": True, "structured_output_strategy": "tool"},
    },
    {
        "name": "llama3-1-70b-instruct-v1",
        "icon": "logos/meta.svg",
        "args": {"stream": True, "structured_output_strategy": "tool"},
    },
    {"name": "gpt-4.1", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "gpt-4o", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "gpt-4.1-mini", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "gpt-4.1-nano", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "gpt-5", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "o1", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "o1-mini", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "o3-mini", "icon": "logos/openai.svg", "args": {"stream": True}},
]

MODEL_CHOICES = [model["name"] for model in MODEL_CHOICES_ARGS]
DEFAULT_MODEL = MODEL_CHOICES[8]


class Agent(ControlNode):
    """A Griptape Node that provides an interface to interact with a Griptape Agent.

    This node facilitates communication with a Griptape Agent, allowing for
    sending prompts and receiving streamed responses. It can initialize a new
    agent or operate on an existing agent representation passed as input.

    Attributes:
        Inherits parameters and methods from ControlNode.
        Defines specific parameters for agent configuration (model, tools, rulesets),
        prompting, context, and output handling.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the ExampleAgent node, setting up its parameters and UI elements.

        This involves defining input/output parameters, grouping related settings,
        and establishing default values and behaviors.
        """
        super().__init__(**kwargs)

        # -- Converters --
        # Converters modify parameter values before they are used by the node's logic.
        def strip_whitespace(value: str) -> str:
            """Removes leading and trailing whitespace from a string value.

            Args:
                value: The input string.

            Returns:
                The string with whitespace stripped, or the original value if empty/None.
            """
            if not value:
                return value
            return value.strip()

        # --- Parameter Definitions ---

        # Parameter to input an existing agent's state or output the final state.
        self.add_parameter(
            Parameter(
                name="agent",
                type="Agent",
                input_types=["Agent"],
                output_type="Agent",
                tooltip="Create a new agent, or continue a chat with an existing agent.",
                default_value=None,
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )
        # Selection for the Griptape Cloud model.
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str", "Prompt Model Config"],
                default_value=DEFAULT_MODEL,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                tooltip="Choose a model, or connect a Prompt Model Configuration",
                traits={Options(choices=MODEL_CHOICES)},
                ui_options={"display_name": "prompt model", "data": MODEL_CHOICES_ARGS},
            )
        )
        # Main prompt input for the agent.
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="The main text prompt to send to the agent.",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Talk with the Agent.",
                },
                converters=[strip_whitespace],
            )
        )

        # Optional additional context for the prompt.
        self.add_parameter(
            Parameter(
                "additional_context",
                input_types=["str", "int", "float", "dict"],
                type="str",
                tooltip=(
                    "Additional context to provide to the agent.\nEither a string, or dictionary of key-value pairs."
                ),
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "Any additional context for the Agent."},
            )
        )

        self.add_parameter(
            ParameterList(
                name="tools",
                input_types=["Tool", "list[Tool]"],
                default_value=[],
                tooltip="Connect Griptape Tools for the agent to use.\nOr connect individual tools.",
                allowed_modes={ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            ParameterList(
                name="rulesets",
                input_types=["Ruleset", "list[Ruleset]"],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                default_value=[],
                allowed_modes={ParameterMode.INPUT},
            )
        )

        # Parameter for output schema
        self.add_parameter(
            Parameter(
                name="output_schema",
                input_types=["json"],
                type="json",
                tooltip="Optional JSON schema for structured output validation.",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
                ui_options={"hide_property": True},
            )
        )

        # Parameter for the agent's final text output.
        self.add_parameter(
            Parameter(
                name="output",
                type="str",
                default_value="",
                tooltip="The final text response from the agent.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Agent response", "markdown": False},
            )
        )

        # Group for logging information.
        with ParameterGroup(name="Logs") as logs_group:
            Parameter(name="include_details", type="bool", default_value=False, tooltip="Include extra details.")

            Parameter(
                name="logs",
                type="str",
                tooltip="Displays processing logs and detailed events if enabled.",
                ui_options={"multiline": True, "placeholder_text": "Logs"},
                allowed_modes={ParameterMode.OUTPUT},
            )
        logs_group.ui_options = {"hide": True}  # Hide the logs group by default.

        self.add_node_element(logs_group)

    # --- Helper Methods ---

    def _update_output_type_and_validate_connections(self, new_output_type: str) -> None:
        """Update the output parameter type and remove incompatible connections.

        Args:
            new_output_type: The new output type to set (e.g., "json" or "str")
        """
        output_param = self.get_parameter_by_name("output")
        if output_param is None:
            return

        # Update output parameter type
        output_param.output_type = new_output_type
        output_param.type = new_output_type

        # Get outgoing connections from the output parameter
        connections = GriptapeNodes.FlowManager().get_connections()
        outgoing_for_node = connections.outgoing_index.get(self.name, {})
        connection_ids = outgoing_for_node.get("output", [])

        # Validate type compatibility and remove incompatible connections
        for connection_id in connection_ids:
            connection = connections.connections[connection_id]
            target_param = connection.target_parameter
            target_node = connection.target_node

            # Check if target parameter accepts the new output type
            is_compatible = any(
                ParameterType.are_types_compatible(new_output_type, input_type)
                for input_type in target_param.input_types
            )

            if not is_compatible:
                logger.info(
                    f"Removing incompatible connection: Agent '{self.name}' output ({new_output_type}) to "
                    f"'{target_node.name}.{target_param.name}' (accepts: {target_param.input_types})"
                )

                # Remove the incompatible connection
                GriptapeNodes.handle_request(
                    DeleteConnectionRequest(
                        source_node_name=self.name,
                        source_parameter_name="output",
                        target_node_name=target_node.name,
                        target_parameter_name=target_param.name,
                    )
                )

    # --- UI Interaction Hooks ---

    def after_incoming_connection(
        self, source_node: BaseNode, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        # If an existing agent is connected, hide parameters related to creating a new one.
        if target_parameter.name == "agent":
            params_to_toggle = ["model", "tools", "rulesets"]
            self.hide_parameter_by_name(params_to_toggle)

        if target_parameter.name == "model" and source_parameter.name == "prompt_model_config":
            # Remove the options trait
            target_parameter.remove_trait(trait_type=target_parameter.find_elements_by_type(Options)[0])

            # Check and see if the incoming connection is from a prompt model config or an agent.
            target_parameter.type = source_parameter.type

            # Remove ParameterMode.PROPERTY so it forces the node mark itself dirty & remove the value
            target_parameter.allowed_modes = {ParameterMode.INPUT}

            # Set the display name to be appropriate
            ui_options = target_parameter.ui_options
            ui_options["display_name"] = source_parameter.ui_options.get("display_name", source_parameter.name)
            target_parameter.ui_options = ui_options

        # If additional context is connected, prevent editing via property panel.
        # NOTE: This is a workaround. Ideally this is done automatically.
        if target_parameter.name == "additional_context":
            target_parameter.allowed_modes = {ParameterMode.INPUT}

        if target_parameter.name == "output_schema":
            # When schema is connected, change output type to json and validate connections
            self._update_output_type_and_validate_connections("json")

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        # If the agent connection is removed, show agent creation parameters.
        if target_parameter.name == "agent":
            params_to_toggle = ["model", "tools", "rulesets", "schema"]
            self.show_parameter_by_name(params_to_toggle)

        if target_parameter.name == "output_schema":
            self.set_parameter_value("output_schema", None)
            # When schema is disconnected, change output type back to str and validate connections
            self._update_output_type_and_validate_connections("str")

        if target_parameter.name == "model":
            # Reset the parameter type
            target_parameter.type = "str"

            # Enable PROPERTY so the user can set it
            target_parameter.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY}

            # Sometimes the value is not set to the default value - these are all attempts to get it to work.
            target_parameter.set_default_value(DEFAULT_MODEL)
            target_parameter.default_value = DEFAULT_MODEL
            self.set_parameter_value("model", DEFAULT_MODEL)

            # Add the options trait
            target_parameter.add_trait(Options(choices=MODEL_CHOICES))

            # Change the display name to be appropriate
            ui_options = target_parameter.ui_options
            ui_options["display_name"] = "prompt model"
            target_parameter.ui_options = ui_options

        # If the additional context connection is removed, make it editable again.
        # NOTE: This is a workaround. Ideally this is done automatically.
        if target_parameter.name == "additional_context":
            target_parameter.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY}

        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    # --- Validation ---
    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Performs pre-run validation checks for the node.

        Currently checks if the Griptape Cloud API key is configured if the default
        prompt driver is likely to be used.

        Returns:
            A list of Exception objects if validation fails, otherwise None.
        """
        exceptions = []

        # Check to see if the API key is set.
        api_key = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)

        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions

        # Return any exceptions
        return exceptions if exceptions else None

    def _handle_additional_context(self, prompt: str, additional_context: str | int | float | dict[str, Any]) -> str:  # noqa: PYI041
        """Integrates additional context into the main prompt string.

        - If context is numeric, it's converted to a string and appended.
        - If context is a string, it's appended on a new line.
        - If context is a dictionary, the prompt is treated as a Jinja2 template
          and rendered with the dictionary as variables.

        Args:
            prompt: The base prompt string.
            additional_context: The context to integrate (str, int, float, dict).

        Returns:
            The potentially modified prompt string.
        """
        context = additional_context
        if isinstance(context, (int, float)):
            # If the additional context is a number, we want to convert it to a string.
            context = str(context)
        if isinstance(context, str):
            prompt += f"\n{context!s}"
        elif isinstance(context, dict):
            prompt = Template(prompt).render(context)
        else:
            # For any other type, convert to string and append
            try:
                context_str = str(context)
                prompt += f"\n{context_str}"
            except Exception:
                # If conversion fails, log warning and continue with original prompt
                msg = f"[WARNING] Unable to process additional_context of type {type(context).__name__}, ignoring."
                logger.warning(msg)
                self.append_value_to_parameter("logs", msg)
        return prompt

    # --- Processing ---
    def process(self) -> AsyncResult[Structure]:  # noqa: C901, PLR0915, PLR0912
        """Executes the main logic of the node asynchronously.

        Sets up the Griptape Agent (either new or from input), configures the
        prompt driver, prepares the prompt with context, and then yields
        a lambda function to perform the actual agent interaction via `_process`.
        Handles setting output parameters after execution.

        Yields:
            A lambda function wrapping the call to `_process` for asynchronous execution.

        Returns:
            An AsyncResult indicating the structure being processed (the agent).
        """
        model_input = self.get_parameter_value("model")
        agent = None
        include_details = self.get_parameter_value("include_details")
        default_prompt_driver = GriptapeCloudPromptDriver(
            model=DEFAULT_MODEL,
            api_key=GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR),
            stream=True,
        )

        # Initialize the logs parameter
        self.append_value_to_parameter("logs", "[Processing..]\n")

        # Get any tools
        # tools = self.get_parameter_value("tools")  # noqa: ERA001
        tools = self.get_parameter_list_value("tools")
        if include_details and tools:
            self.append_value_to_parameter("logs", f"[Tools]: {', '.join([tool.name for tool in tools])}\n")

        # Get any rulesets
        rulesets = self.get_parameter_list_value("rulesets")
        if include_details and rulesets:
            self.append_value_to_parameter(
                "logs",
                f"\n[Rulesets]: {', '.join([ruleset.name for ruleset in rulesets])}\n",
            )

        # Get the output schema
        output_schema: str = self.get_parameter_value("output_schema")
        pydantic_schema = None
        if output_schema is not None:
            try:
                pydantic_schema = create_model(output_schema)
            except Exception as e:
                msg = f"[ERROR]: Unable to create output schema model: {e}. Try using the `Create Agent Schema` node to generate a schema."
                self.append_value_to_parameter("logs", msg + "\n")
                logger.error(msg)
                raise

        if include_details and pydantic_schema:
            self.append_value_to_parameter("logs", "[Schema]: Structured output schema provided\n")

        # Get the prompt
        prompt = self.get_parameter_value("prompt")

        # Use any additional context provided by the user.
        additional_context = self.get_parameter_value("additional_context")
        if additional_context:
            prompt = self._handle_additional_context(prompt, additional_context)

        # If the user has connected a prompt, we want to show it in the logs.
        if include_details and prompt:
            self.append_value_to_parameter("logs", f"[Prompt]:\n{prompt}\n")

        # If an agent is provided, we'll use and ensure it's using a PromptTask
        # If a prompt_driver is provided, we'll use that
        # If neither are provided, we'll create a new one with the selected model.
        # Otherwise, we'll just use the default model
        agent = self.get_parameter_value("agent")
        if isinstance(agent, dict):
            # The agent is connected. We'll use that.
            agent = GtAgent().from_dict(agent)
            # make sure the agent is using a PromptTask
            if not isinstance(agent.tasks[0], PromptTask):
                agent.add_task(PromptTask(prompt_driver=default_prompt_driver, output_schema=pydantic_schema))
            else:
                agent.tasks[0].output_schema = pydantic_schema
        elif isinstance(model_input, BasePromptDriver):
            agent = GtAgent(prompt_driver=model_input, tools=tools, rulesets=rulesets, output_schema=pydantic_schema)
        elif isinstance(model_input, str):
            if model_input not in MODEL_CHOICES:
                model_input = DEFAULT_MODEL
            # Get the appropriate args
            args = next((model["args"] for model in MODEL_CHOICES_ARGS if model["name"] == model_input), {})
            # Remove any None values from args
            args = {k: v for k, v in args.items() if v is not None}
            prompt_driver = GriptapeCloudPromptDriver(
                model=model_input,
                api_key=GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR),
                **args,
            )
            agent = GtAgent(prompt_driver=prompt_driver, tools=tools, rulesets=rulesets, output_schema=pydantic_schema)

        if prompt and not prompt.isspace():
            # Run the agent asynchronously
            self.append_value_to_parameter("logs", "[Started processing agent..]\n")
            yield lambda: self._process(agent, prompt)
            self.append_value_to_parameter("logs", "\n[Finished processing agent.]\n")
            try_throw_error(agent.output)
        else:
            self.append_value_to_parameter("logs", "[No prompt provided, creating Agent.]\n")
            self.parameter_output_values["output"] = "Agent created."
        # Set the agent
        self.parameter_output_values["agent"] = agent.to_dict()

    def _process(self, agent: GtAgent, prompt: BaseArtifact | str) -> Structure:  # noqa: C901, PLR0912
        """Performs the synchronous, streaming interaction with the Griptape Agent.

        Iterates through events generated by `agent.run_stream`, updating the
        'output' parameter with text chunks and the 'logs' parameter with
        action details (if enabled).

        Normally we would use the pattern:
        for artifact in Stream(agent).run(prompt):
        But for this example, we'll use the run_stream method to get the events so we can
        show the user when the Agent is using a tool.

        Args:
            agent: The configured Griptape Agent instance.
            prompt: The final prompt string or BaseArtifact to send to the agent.

        Returns:
            The agent structure after processing.
        """
        include_details = self.get_parameter_value("include_details")

        args = [prompt] if prompt else []
        structure_id_stack = []
        active_structure_id = None

        task = agent.tasks[0]
        if not isinstance(task, PromptTask):
            msg = "Agent must have a PromptTask"
            raise TypeError(msg)
        prompt_driver = task.prompt_driver
        prompt_driver.stream = True
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

                # If an Agent uses other Agents (via `StructureRunTool`), we will receive those events too.
                # We want to ignore those events and only show the events for this node's Agent.
                # TODO: https://github.com/griptape-ai/griptape-nodes/issues/984
                if agent.id == active_structure_id:
                    # Check for cancellation request
                    if self.is_cancellation_requested:
                        self.append_value_to_parameter("logs", "\n[Agent execution cancelled by user.]\n")
                        return agent

                    # If the artifact is a TextChunkEvent, append it to the output parameter.
                    if isinstance(event, TextChunkEvent):
                        self.append_value_to_parameter("output", value=event.token)
                        if include_details:
                            self.append_value_to_parameter("logs", value=event.token)

                    # If the artifact is an ActionChunkEvent, append it to the logs parameter.
                    if include_details and isinstance(event, ActionChunkEvent) and event.name:
                        self.append_value_to_parameter("logs", f"\n[Using tool {event.name}: ({event.path})]\n")
        else:
            agent.run(*args)
            agent_output = agent.output
            if isinstance(agent_output, ModelArtifact):
                self.set_parameter_value("output", agent_output.value.model_dump_json())
            else:
                self.set_parameter_value("output", str(agent_output))
            try_throw_error(agent.output)
        return agent
