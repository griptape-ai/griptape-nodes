from typing import Any, Self

from griptape.artifacts import BaseArtifact
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.events import ActionChunkEvent, TextChunkEvent
from griptape.structures import Structure
from griptape.structures.agent import Agent as GtAgent
from jinja2 import Template

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.error_utils import try_throw_error

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
DEFAULT_MODEL = "gpt-4.1-mini"
CONNECTED_CHOICE = "use incoming config"
MODELS = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4.5-preview",
    "o1",
    "o1-mini",
    "o3-mini",
    CONNECTED_CHOICE,
]


class ExampleAgent(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # -- Converters --
        # Converts should take one positional argument of any type, and can return anything!
        def strip_whitespace(value: str) -> str:
            # This is a simple converter that strips whitespace from the input string.
            if not value:
                return value
            return value.strip()

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
        # -- Parameters --
        # Parameters are the inputs and outputs of the node. They can be used to connect to other nodes.
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                output_type="str",
                type="str",
                tooltip="None",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Talk with the Agent."},
                converters=[strip_whitespace],
            )
        )
        self.add_parameter(
            Parameter(
                "additional context",
                input_types=["str", "int", "float", "dict"],
                type="str",
                tooltip="Additional context to provide to the agent.\nEither a string, or dictionary of key-value pairs.",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "Any additional context for the Agent."},
            )
        )

        self.add_parameter(
            Parameter(
                name="model",
                type="str",
                input_types=["str"],
                tooltip="Models to choose from.",
                default_value=DEFAULT_MODEL,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODELS)},
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt model config",
                input_types=["Prompt Model Config"],
                type="Prompt Model Config",
                tooltip="Connect prompt model config. If not supplied, we will use the Griptape Cloud Prompt Model.",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
                ui_options={"hide": True},
            )
        )
        with ParameterGroup(group_name="Advanced options") as advanced_group:
            ParameterList(
                name="tools",
                input_types=["Tool"],
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.INPUT},
            )
            ParameterList(
                name="rulesets",
                input_types=["Ruleset", "List[Ruleset]"],
                tooltip="Rulesets to apply to the agent to control its behavior.",
                allowed_modes={ParameterMode.INPUT},
            )
        advanced_group.ui_options = {"hide": True}  # Hide the advanced group by default.
        self.add_node_element(advanced_group)

        self.add_parameter(
            Parameter(
                name="output",
                type="str",
                default_value="",
                tooltip="What the agent said.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"multiline": True, "placeholder_text": "Agent response"},
            )
        )

        # Group the logs into a separate group the user can open and close.
        # This is a good way to keep the UI clean and organized.
        with ParameterGroup(group_name="Logs") as logs_group:
            Parameter(
                name="include prompt", type="bool", default_value=False, tooltip="Include the prompt in the logs."
            )
            Parameter(
                name="include model config",
                type="bool",
                default_value=False,
                tooltip="Include the model config in the logs.",
            )
            Parameter(name="include tools", type="bool", default_value=False, tooltip="Include the tools in the logs.")
            Parameter(
                name="include rulesets", type="bool", default_value=False, tooltip="Include the rulesets in the logs."
            )
            Parameter(
                name="include output", type="bool", default_value=False, tooltip="Include the output in the logs."
            )
            Parameter(
                name="logs",
                type="str",
                tooltip="None",
                default_value="Node hasn't begun yet",
                ui_options={"multiline": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        logs_group.ui_options = {"hide": True}  # Hide the logs group by default.

        self.add_node_element(logs_group)

    # -- After Changing a Parameter --
    # This is called after a parameter is set. We can use this to show/hide parameters
    # based on the value of other parameters.
    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        # Model
        # If user sets the model to CONNECTED_CHOICE, we want to show the prompt_model_settings parameter.
        if parameter.name == "model":
            # Find the prompt_model_settings parameter and hide it
            prompt_model_settings_param = self.get_parameter_by_name("prompt model config")
            if value == CONNECTED_CHOICE and prompt_model_settings_param:
                prompt_model_settings_param._ui_options["hide"] = False
            elif value != CONNECTED_CHOICE and prompt_model_settings_param:
                prompt_model_settings_param._ui_options["hide"] = True

            # Add this to the modified parameters set so we can cascade the change.
            modified_parameters_set.add("prompt model config")

        return super().after_value_set(parameter, value, modified_parameters_set)

    # -- After Connections --
    # These are called after a connection is made to or disconnected from this node.
    # We can use this to show/hide parameters

    def after_incoming_connection(
        self, source_node: Self, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        # Agent
        # If the user connects to the agent, we want to hide some parameters.
        if target_parameter.name == "agent":
            params_to_toggle = ["model", "tools", "rulesets", "prompt model config"]
            groups_to_toggle = ["Advanced options"]
            for group_name in groups_to_toggle:
                group = self.get_group_by_name_or_element_id(group_name)
                if group:
                    group.ui_options["hide"] = True
            for param_name in params_to_toggle:
                param = self.get_parameter_by_name(param_name)
                if param:
                    param._ui_options["hide"] = True

        # Prompt Driver
        # If the user connects to the prompt_model_settings, we want to hide the model parameter.
        if target_parameter.name == "prompt model config":
            # Find the model parameter and hide it
            model_param = self.get_parameter_by_name("model")
            if model_param:
                model_param._ui_options["hide"] = True

        # Additional Context
        # If the user connects to the additional context, make it not editable.
        if target_parameter.name == "additional context":
            target_parameter.allowed_modes = {ParameterMode.INPUT}

        # Default return
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self, source_node: Self, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        # Agent
        # If the user connects to the agent, we want to show some parameters.
        if target_parameter.name == "agent":
            groups_to_toggle = ["Advanced options"]
            for group_name in groups_to_toggle:
                group = self.get_group_by_name_or_element_id(group_name)
                if group:
                    group.ui_options["hide"] = False

            params_to_toggle = ["model", "tools", "rulesets", "prompt model config"]
            for param_name in params_to_toggle:
                param = self.get_parameter_by_name(param_name)
                if param:
                    param._ui_options["hide"] = False
        # If the user connects to the prompt_model_settings, we want to hide the model parameter.
        if target_parameter.name == "prompt model config":
            # Find the model parameter and hide it
            model_param = self.get_parameter_by_name("model")
            if model_param:
                model_param._ui_options["hide"] = False

        # Additional Context
        # If the user connects to the additional context, make it  editable.
        if target_parameter.name == "additional context":
            target_parameter.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY}

        # Default return
        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    # -- Validation --
    # This is called before the node is run. We can use this to validate the parameters.
    def validate_node(self) -> list[Exception] | None:
        exceptions = []

        # Check to see if the API key is set.
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)

        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions

        # Return any exceptions
        return exceptions if exceptions else None

    def _handle_additonal_context(self, prompt, additional_context: str | int | float | dict[str, Any]) -> str:  # noqa: PYI041
        context = additional_context
        if isinstance(context, (int, float)):
            # If the additional context is a number, we want to convert it to a string.
            context = str(context)
        if isinstance(context, str):
            prompt += f"\n{context!s}"
        elif isinstance(context, dict):
            prompt = Template(prompt).render(context)
        return prompt

    # -- Processing --
    # This is called when the node is run. We can use this to process the node.
    def process(self) -> AsyncResult[Structure]:
        # Get the parameters from the node
        params = self.parameter_values
        self.append_value_to_parameter("logs", "[Processing..]\n")

        # Grab toggles for logging events
        include_rulesets = self.get_parameter_value("include rulesets")
        include_prompt = self.get_parameter_value("include prompt")
        include_model_config = self.get_parameter_value("include model config")
        include_tools = self.get_parameter_value("include tools")

        # For this node, we'll going use the GriptapeCloudPromptDriver if no driver is provided.
        # If a driver is provided, we'll use that.
        prompt_model_settings = params.get("prompt model config", None)
        if not prompt_model_settings:
            # Grab the appropriate parameters
            model = params.get("model", DEFAULT_MODEL)
            if include_model_config:
                self.append_value_to_parameter("logs", f"\n[Model]: {params.get('model')}\n")

            prompt_model_settings = GriptapeCloudPromptDriver(
                model=model,
                api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR),
                stream=True,
            )

        if include_model_config:
            self.append_value_to_parameter("logs", f"\n[Model config]: {prompt_model_settings}\n")

        # Get any tools
        tools = params.get("tools", [])
        if include_tools and tools:
            self.append_value_to_parameter("logs", f"\n[Tools]: {', '.join([tool.name for tool in tools])}\n")

        # Get any rulesets
        rulesets = params.get("rulesets", [])
        if include_rulesets and rulesets:
            self.append_value_to_parameter(
                "logs", f"\n[Rulesets]: {', '.join([ruleset.name for ruleset in rulesets])}\n"
            )

        # Get the prompt
        prompt = params.get("prompt", "")

        # Use any additional context provided by the user.
        additional_context = params.get("additional context", None)
        if additional_context:
            prompt = self._handle_additonal_context(prompt, additional_context)

        # If the user has connected a prompt, we want to show it in the logs.
        if include_prompt and prompt:
            self.append_value_to_parameter("logs", f"\n[Prompt]:\n{prompt}]\n")

        # Create the agent
        agent = None
        agent_dict = params.get("agent", None)
        if not agent_dict:
            agent = GtAgent(prompt_driver=prompt_model_settings, tools=tools, rulesets=rulesets)
        else:
            agent = GtAgent.from_dict(agent_dict)

        # Run the agent asynchronously
        self.append_value_to_parameter("logs", "\n[Started processing agent..]\n\n")
        yield lambda: self._process(agent, prompt)
        self.append_value_to_parameter("logs", "\n\n[Finished processing agent.]")

        # Set the agent
        self.parameter_output_values["agent"] = agent.to_dict()

        try_throw_error(agent.output)

    def _process(self, agent: GtAgent, prompt: BaseArtifact | str) -> Structure:
        # Normally we would use the pattern:
        # for artifact in Stream(agent).run(prompt):
        # But for this example, we'll use the run_stream method to get the events so we can
        # show the user when the Agent is using a tool.

        # Grab toggles for logging events
        include_tools = self.get_parameter_value("include tools")
        include_output = self.get_parameter_value("include output")

        for event in agent.run_stream(prompt, event_types=[TextChunkEvent, ActionChunkEvent]):
            # If the artifact is a TextChunkEvent, append it to the output parameter.
            if isinstance(event, TextChunkEvent):
                self.append_value_to_parameter("output", value=event.token)
                if include_output:
                    self.append_value_to_parameter("logs", value=event.token)

            # If the artifact is an ActionChunkEvent, append it to the logs parameter.
            if include_tools and isinstance(event, ActionChunkEvent) and event.name:
                self.append_value_to_parameter("logs", f"\n[Using tool {event.name}: ({event.path})]\n")

        return agent
