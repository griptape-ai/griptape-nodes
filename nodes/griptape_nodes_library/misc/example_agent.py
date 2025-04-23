from typing import Any, Self

from griptape.artifacts import BaseArtifact
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.events import ActionChunkEvent, TextChunkEvent
from griptape.structures import Structure
from griptape.structures.agent import Agent as GtAgent
from griptape.utils import Stream

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.error_utils import try_throw_error

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
DEFAULT_MODEL = "gpt-4.1-mini"
MODELS = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4.5-preview",
    "o1",
    "o1-mini",
    "o3-mini",
    "other",
]  # currently only gpt-4o is supported


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
                name="prompt model settings",
                input_types=["Prompt Model Settings"],
                type="Prompt Model Settings",
                tooltip="Connect prompt model settings. If not supplied, we will use the Griptape Cloud Prompt Model.",
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
                name="agent",
                type="Agent",
                input_types=["Agent", "dict"],
                output_type="Agent",
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

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
        # If user sets the model to "other", we want to show the prompt_model_settings parameter.
        if parameter.name == "model":
            # Find the prompt_model_settings parameter and hide it
            prompt_model_settings_param = self.get_parameter_by_name("prompt model settings")
            if value == "other" and prompt_model_settings_param:
                prompt_model_settings_param._ui_options["hide"] = False
            elif value != "other" and prompt_model_settings_param:
                prompt_model_settings_param._ui_options["hide"] = True

            # Add this to the modified parameters set so we can cascade the change.
            modified_parameters_set.add("prompt model settings")

        return super().after_value_set(parameter, value, modified_parameters_set)

    # -- After Connections --
    # These are called after a connection is made to or disconnected from this node.
    # We can use this to show/hide parameters

    def after_incoming_connection(
        self, source_node: Self, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        # Prompt Driver
        # If the user connects to the prompt_model_settings, we want to hide the model parameter.
        if target_parameter.name == "prompt model settings":
            # Find the model parameter and hide it
            model_param = self.get_parameter_by_name("model")
            if model_param:
                model_param._ui_options["hide"] = True

        # Default return
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self, source_node: Self, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        # If the user connects to the prompt_model_settings, we want to hide the model parameter.
        if target_parameter.name == "prompt model settings":
            # Find the model parameter and hide it
            model_param = self.get_parameter_by_name("model")
            if model_param:
                model_param._ui_options["hide"] = False

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

    # -- Processing --
    # This is called when the node is run. We can use this to process the node.
    def process(self) -> AsyncResult[Structure]:
        # Get the parameters from the node
        params = self.parameter_values

        # Send the logs to the logs parameter.
        self.append_value_to_parameter("logs", "Checking for prompt driver..\n")

        # For this node, we'll going use the GriptapeCloudPromptDriver if no driver is provided.
        # If a driver is provided, we'll use that.
        prompt_model_settings = params.get("prompt model settings", None)

        if not prompt_model_settings:
            self.append_value_to_parameter("logs", "Using GriptapeCloudPromptDriver.\n")

            # Grab the appropriate parameters
            model = params.get("model", DEFAULT_MODEL)
            self.append_value_to_parameter("logs", f"Using model: {model}\n")

            prompt_model_settings = GriptapeCloudPromptDriver(
                model=model,
                api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR),
                stream=True,
            )
        else:
            self.append_value_to_parameter("logs", "Using provided prompt driver.\n")

        self.append_value_to_parameter("logs", "\nCreating agent..\n")

        # Create the agent
        agent = GtAgent(prompt_driver=prompt_model_settings)

        # Get the prompt
        prompt = params.get("prompt", "")

        # Run the agent asynchronously
        self.append_value_to_parameter("logs", "Started processing agent..\n")
        yield lambda: self._process(agent, prompt)
        self.append_value_to_parameter("logs", "Finished processing agent.\n")

        try_throw_error(agent.output)

    def _process(self, agent: GtAgent, prompt: BaseArtifact | str) -> Structure:
        # try a different pattern
        # for event in agent.run_stream(prompt, event_types=[TextChunkEvent, ActionChunkEvent]):
        #     # If the artifact is a TextChunkEvent, append it to the output parameter.
        #     if isinstance(event, TextChunkEvent):
        #         self.append_value_to_parameter("output", value=event.token)  # noqa: ERA001

        #     # If the artifact is an ActionChunkEvent, append it to the logs parameter.
        #     elif isinstance(event, ActionChunkEvent):  # noqa: ERA001
        #         self.append_value_to_parameter("logs", f"{event.name}.{event.tag} ({event.path})\n")  # noqa: ERA001
        stream = Stream(agent, event_types=[TextChunkEvent, ActionChunkEvent])
        for artifact in stream.run(prompt):
            # If the artifact is a TextChunkEvent, append it to the output parameter.
            self.append_value_to_parameter("output", value=artifact.value)

            # If the artifact is an ActionChunkEvent, append it to the logs parameter.
            # self.append_value_to_parameter("logs", f"{artifact=}\n")  # noqa: ERA001
        return agent
