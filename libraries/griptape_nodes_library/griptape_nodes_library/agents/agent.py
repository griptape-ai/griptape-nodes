"""Defines the ExampleAgent node, providing an interface to interact with a Griptape Agent.

This node allows users to create a new Griptape Agent or continue interaction
with an existing one. It defaults to using the Griptape Cloud prompt driver
but supports connecting custom prompt_model_configurations. It handles parameters
for tools, rulesets, prompts, and streams output back to the user interface.
"""

from typing import Any

from griptape.artifacts import BaseArtifact
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.events import ActionChunkEvent, FinishStructureRunEvent, StartStructureRunEvent, TextChunkEvent
from griptape.structures import Structure
from griptape.structures.agent import Agent as GtAgent
from jinja2 import Template

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.error_utils import try_throw_error

# --- Constants ---
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
CONNECTED_CHOICE = "use incoming config"
MODEL_CHOICES = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4.5-preview",
    "o1",
    "o1-mini",
    "o3-mini",
    CONNECTED_CHOICE,
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
                input_types=["Agent", "dict"],
                output_type="Agent",
                tooltip="Create a new agent, or continue a chat with an existing agent.",
                default_value=None,
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
                ui_options={"multiline": True, "placeholder_text": "Talk with the Agent."},
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

        # Selection for the Griptape Cloud model.
        self.add_parameter(
            Parameter(
                name="model",
                type="str",
                input_types=["str"],
                tooltip="Models to choose from.",
                default_value=DEFAULT_MODEL,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODEL_CHOICES)},
            )
        )

        # Input for a pre-configured prompt model driver/config.
        self.add_parameter(
            Parameter(
                name="prompt_model_config",
                input_types=["Prompt Model Config"],
                type="Prompt Model Config",
                tooltip="Connect prompt_model_config. If not supplied, we will use the Griptape Cloud Prompt Model.",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
                ui_options={"hide": False},  # TODO: https://github.com/griptape-ai/griptape-nodes/issues/877
            )
        )

        # Group for less commonly used configuration options.
        with ParameterGroup(group_name="Advanced options") as advanced_group:
            ParameterList(
                name="tools",
                input_types=["Tool"],
                default_value=[],
                tooltip="Connect Griptape Tools for the agent to use.\nOr connect individual tools.",
                allowed_modes={ParameterMode.INPUT},
            )
            ParameterList(
                name="rulesets",
                input_types=["Ruleset", "List[Ruleset]"],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                default_value=[],
                allowed_modes={ParameterMode.INPUT},
            )

        advanced_group.ui_options = {"hide": True}  # Hide the advanced group by default.
        self.add_node_element(advanced_group)

        # Parameter for the agent's final text output.
        self.add_parameter(
            Parameter(
                name="output",
                type="str",
                default_value="",
                tooltip="The final text response from the agent.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Agent response"},
            )
        )

        # Group for logging information.
        with ParameterGroup(group_name="Logs") as logs_group:
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

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        """Handles UI updates after a parameter's value is changed via the property panel.

        Specifically, it shows/hides the 'prompt_model_config' input based on
        whether the 'model' dropdown is set to use an incoming configuration.

        Args:
            parameter: The Parameter whose value was changed.
            value: The new value assigned to the parameter.
            modified_parameters_set: A set to which names of parameters whose UI state
                                     might have changed should be added. This helps the
                                     UI framework know what needs updating.
        """
        # Show 'prompt_model_config' input only if 'model' is set to CONNECTED_CHOICE.
        if parameter.name == "model":
            """
            TODO: https://github.com/griptape-ai/griptape-nodes/issues/878

            """
            prompt_model_settings_param = self.get_parameter_by_name("prompt_model_config")
            if value == CONNECTED_CHOICE and prompt_model_settings_param:
                if prompt_model_settings_param._ui_options["hide"]:
                    modified_parameters_set.add("prompt_model_config")
                prompt_model_settings_param._ui_options["hide"] = False
                return None
            if value != CONNECTED_CHOICE and prompt_model_settings_param:
                if not prompt_model_settings_param._ui_options["hide"]:
                    modified_parameters_set.add("prompt_model_config")
                prompt_model_settings_param._ui_options["hide"] = True
                return None

        return super().after_value_set(parameter, value, modified_parameters_set)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        """Handles UI updates after an incoming connection is made to this node.

        - Hides agent creation parameters (model, tools, rulesets, advanced group)
          if an existing agent is connected.
        - Hides the 'model' dropdown if a 'prompt_model_config' is connected.
        - Makes 'additional context' read-only if connected (value comes from input).

        Args:
            source_node: The node connecting to this node.
            source_parameter: The parameter on the source node providing the connection.
            target_parameter: The parameter on this node receiving the connection.
            modified_parameters_set: The set of parameters that have changed
        """
        # If an existing agent is connected, hide parameters related to creating a new one.
        if target_parameter.name == "agent":
            groups_to_toggle = ["Advanced options"]
            for group_name in groups_to_toggle:
                group = self.get_group_by_name_or_element_id(group_name)
                if group:
                    group.ui_options["hide"] = True
                    modified_parameters_set.add(group_name)

            params_to_toggle = ["model", "tools", "rulesets", "prompt_model_config"]
            for param_name in params_to_toggle:
                param = self.get_parameter_by_name(param_name)
                if param:
                    param._ui_options["hide"] = True
                    modified_parameters_set.add(param_name)

        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/878
        # If a prompt_model_config is connected, hide the manual model selector.
        if target_parameter.name == "prompt_model_config":
            model_param = self.get_parameter_by_name("model")
            if model_param:
                model_param._ui_options["hide"] = True
                modified_parameters_set.add("model")
        # If additional context is connected, prevent editing via property panel.
        # NOTE: This is a workaround. Ideally this is done automatically.
        if target_parameter.name == "additional_context":
            target_parameter.allowed_modes = {ParameterMode.INPUT}
            modified_parameters_set.add("additional_context")

        return super().after_incoming_connection(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )

    def after_incoming_connection_removed(  # noqa: C901
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        """Handles UI updates after an incoming connection to this node is removed.

        Reverses the logic of `after_incoming_connection`:
        - Shows agent creation parameters if the agent connection is removed.
        - Shows the 'model' dropdown if the 'prompt_model_config' connection is removed
          (unless an agent is still connected).
        - Makes 'additional context' editable again if its connection is removed.

        Args:
            source_node: The node that was connected.
            source_parameter: The parameter on the source node that was connected.
            target_parameter: The parameter on this node that was disconnected.
            modified_parameters_set: The set of parameters that have changed
        """
        # If the agent connection is removed, show agent creation parameters.
        if target_parameter.name == "agent":
            groups_to_toggle = ["Advanced options"]
            for group_name in groups_to_toggle:
                group = self.get_group_by_name_or_element_id(group_name)
                if group:
                    group.ui_options["hide"] = False
                    modified_parameters_set.add(group.group_name)

            params_to_toggle = ["model", "tools", "rulesets", "prompt_model_config"]
            for param_name in params_to_toggle:
                param = self.get_parameter_by_name(param_name)
                if param:
                    # Special case: Don't unhide 'prompt_model_config' if model is not CONNECTED_CHOICE
                    if param_name == "prompt_model_config":
                        model_value = self.get_parameter_value("model")
                        if model_value != CONNECTED_CHOICE:
                            continue  # Keep it hidden if model isn't set to use connection

                    param._ui_options["hide"] = False
                    modified_parameters_set.add(param.name)

        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/878
        # If the prompt_model_config connection is removed, show the model dropdown,
        if target_parameter.name == "prompt_model_config":
            # Find the model parameter and hide it
            model_param = self.get_parameter_by_name("model")
            if model_param:
                model_param._ui_options["hide"] = False
                modified_parameters_set.add(model_param.name)

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

    def process(self) -> AsyncResult[Structure]:
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
        # Get the parameters from the node
        params = self.parameter_values
        # Grab toggles for logging events
        include_details = self.get_parameter_value("include_details")

        # Initialize the logs parameter
        self.append_value_to_parameter("logs", "[Processing..]\n")

        # For this node, we'll going use the GriptapeCloudPromptDriver if no driver is provided.
        # If a driver is provided, we'll use that.
        prompt_model_settings = self.get_parameter_value("prompt_model_config")
        if not prompt_model_settings:
            # Grab the appropriate parameters
            model = self.get_parameter_value("model")
            if include_details:
                self.append_value_to_parameter("logs", f"[Model]: {model}\n")

            prompt_model_settings = GriptapeCloudPromptDriver(
                model=model,
                api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR),
                stream=True,
            )

        if include_details:
            self.append_value_to_parameter("logs", f"[Model config]: {prompt_model_settings}\n")

        # Get any tools
        # tools = self.get_parameter_value("tools")  # noqa: ERA001
        tools = [tool for tool in params.get("tools", []) if tool]
        if include_details and tools:
            self.append_value_to_parameter("logs", f"[Tools]: {', '.join([tool.name for tool in tools])}\n")

        # Get any rulesets
        # rulesets = self.get_parameter_value("rulesets")  # noqa: ERA001
        rulesets = [ruleset for ruleset in params.get("rulesets", []) if ruleset]
        if include_details and rulesets:
            self.append_value_to_parameter(
                "logs", f"\n[Rulesets]: {', '.join([ruleset.name for ruleset in rulesets])}\n"
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

        # Create the agent
        agent = None
        agent_dict = self.get_parameter_value("agent")
        if not agent_dict:
            agent = GtAgent(prompt_driver=prompt_model_settings, tools=tools, rulesets=rulesets)
        else:
            agent = GtAgent.from_dict(agent_dict)

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
