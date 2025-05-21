"""Defines the ExampleAgent node, providing an interface to interact with a Griptape Agent.

This node allows users to create a new Griptape Agent or continue interaction
with an existing one. It defaults to using the Griptape Cloud prompt driver
but supports connecting custom prompt_model_configurations. It handles parameters
for tools, rulesets, prompts, and streams output back to the user interface.
"""

from typing import Any

from griptape.artifacts import BaseArtifact
from griptape.drivers.prompt.base_prompt_driver import BasePromptDriver
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.events import ActionChunkEvent, FinishStructureRunEvent, StartStructureRunEvent, TextChunkEvent
from griptape.structures import Structure
from griptape.tasks import PromptTask
from jinja2 import Template

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.agents.griptape_nodes_agent import GriptapeNodesAgent as GtAgent
from griptape_nodes_library.utils.error_utils import try_throw_error

# --- Constants ---
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
MODEL_CHOICES = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4.5-preview",
    "o1",
    "o1-mini",
    "o3-mini",
]
DEFAULT_MODEL = MODEL_CHOICES[0]


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
                ui_options={"display_name": "prompt model"},
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
                input_types=["Tool"],
                default_value=[],
                tooltip="Connect Griptape Tools for the agent to use.\nOr connect individual tools.",
                allowed_modes={ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            ParameterList(
                name="rulesets",
                input_types=["Ruleset"],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                default_value=[],
                allowed_modes={ParameterMode.INPUT},
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

    # --- UI Interaction Hooks ---

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        # If an existing agent is connected, hide parameters related to creating a new one.
        if target_parameter.name == "agent":
            params_to_toggle = ["model", "tools", "rulesets"]
            self.hide_parameter_by_name(params_to_toggle)
            for param_name in params_to_toggle:
                modified_parameters_set.add(param_name)

        if target_parameter.name == "model" and source_parameter.name == "prompt_model_config":
            # Remove the options trait
            target_parameter.remove_trait(trait_type=target_parameter.find_elements_by_type(Options)[0])

            # Check and see if the incoming connection is from a prompt model config or an agent.
            target_parameter.type = source_parameter.type

            # Remove ParameterMode.PROPERTY so it forces the node mark itself dirty & remove the value
            target_parameter.allowed_modes = {ParameterMode.INPUT}

            # Set the display name to be appropriate
            target_parameter._ui_options["display_name"] = source_parameter.ui_options.get(
                "display_name", source_parameter.name
            )

            # make sure we update the model
            modified_parameters_set.add("model")

        # If additional context is connected, prevent editing via property panel.
        # NOTE: This is a workaround. Ideally this is done automatically.
        if target_parameter.name == "additional_context":
            target_parameter.allowed_modes = {ParameterMode.INPUT}
            modified_parameters_set.add("additional_context")

        return super().after_incoming_connection(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        # If the agent connection is removed, show agent creation parameters.
        if target_parameter.name == "agent":
            params_to_toggle = ["model", "tools", "rulesets"]
            self.show_parameter_by_name(params_to_toggle)
            for param_name in params_to_toggle:
                modified_parameters_set.add(param_name)

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
            target_parameter._ui_options["display_name"] = "prompt model"

            modified_parameters_set.add("model")

        # If the additional context connection is removed, make it editable again.
        # NOTE: This is a workaround. Ideally this is done automatically.
        if target_parameter.name == "additional_context":
            target_parameter.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY}
            modified_parameters_set.add(target_parameter.name)

        return super().after_incoming_connection_removed(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )

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
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)

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
    def process(self) -> AsyncResult[Structure]:  # noqa: C901
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
            model=DEFAULT_MODEL, api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR), stream=True
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
                agent.add_task(PromptTask(prompt_driver=default_prompt_driver))
        elif isinstance(model_input, BasePromptDriver):
            agent = GtAgent(prompt_driver=model_input, tools=tools, rulesets=rulesets)
        elif isinstance(model_input, str):
            if model_input not in MODEL_CHOICES:
                model_input = DEFAULT_MODEL
            prompt_driver = GriptapeCloudPromptDriver(
                model=model_input, api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR), stream=True
            )
            agent = GtAgent(prompt_driver=prompt_driver, tools=tools, rulesets=rulesets)

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

    def _process(self, agent: GtAgent, prompt: BaseArtifact | str) -> Structure:
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
                # If the artifact is a TextChunkEvent, append it to the output parameter.
                if isinstance(event, TextChunkEvent):
                    self.append_value_to_parameter("output", value=event.token)
                    if include_details:
                        self.append_value_to_parameter("logs", value=event.token)

                # If the artifact is an ActionChunkEvent, append it to the logs parameter.
                if include_details and isinstance(event, ActionChunkEvent) and event.name:
                    self.append_value_to_parameter("logs", f"\n[Using tool {event.name}: ({event.path})]\n")

        return agent
