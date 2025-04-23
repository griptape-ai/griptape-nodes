from typing import Any, Self

from griptape.artifacts import BaseArtifact
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.structures import Structure
from griptape.structures.agent import Agent as GtAgent
from griptape.utils import Stream

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.error_utils import try_throw_error

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
DEFAULT_MODEL = "gpt-4o"
MODELS = ["gpt-4o", "other"]  # currently only gpt-4o is supported


class ExampleAgent(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Converters should take one positional argument of any type, and can return anything!
        def strip_whitespace(value: str) -> str:
            # This is a simple converter that strips whitespace from the input string.
            if not value:
                return value
            return value.strip()

        # Create the Prompt parameter first - This is the most important one for the agent.
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
                input_types=["str"],
                type="str",
                tooltip="Models to choose from.",
                default_value=DEFAULT_MODEL,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=MODELS)},
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt_driver",
                input_types=["PromptDriver"],
                type="PromptDriver",
                tooltip="This is a prompt driver. If not supplied, we will use the Griptape Cloud Prompt Driver.",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
                ui_options={"hide": True},
            )
        )

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
        # If user sets the model to "other", we want to show the prompt_driver parameter.
        model_value = self.parameter_values.get("model")
        prompt_driver_param = self.get_parameter_by_name("prompt_driver")
        if model_value == "other" and prompt_driver_param:
            prompt_driver_param._ui_options["hide"] = False
        elif model_value != "other" and prompt_driver_param:
            prompt_driver_param._ui_options["hide"] = True

        return super().after_value_set(parameter, value, modified_parameters_set)

    def after_incoming_connection(
        self, source_node: Self, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        # If the user connects to the prompt_driver, we want to hide the model parameter.
        if target_parameter.name == "prompt_driver":
            # Find the model parameter and hide it
            model_param = self.get_parameter_by_name("model")
            if model_param:
                model_param._ui_options["hide"] = True
        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self, source_node: Self, source_parameter: Parameter, target_parameter: Parameter
    ) -> None:
        # If the user connects to the prompt_driver, we want to hide the model parameter.
        if target_parameter.name == "prompt_driver":
            # Find the model parameter and hide it
            model_param = self.get_parameter_by_name("model")
            if model_param:
                model_param._ui_options["hide"] = False

        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def validate_node(self) -> list[Exception] | None:
        # TODO(kate): Figure out how to wrap this so it's easily repeatable
        exceptions = []
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        # No need for the api key. These exceptions caught on other nodes.
        if self.parameter_values.get("agent", None) and self.parameter_values.get("driver", None):
            return None
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        return exceptions if exceptions else None

    def process(self) -> AsyncResult[Structure]:
        # Get the parameters from the node
        params = self.parameter_values

        # For this node, we'll going use the GriptapeCloudPromptDriver if no driver is provided.
        # If a driver is provided, we'll use that.

        # Send the logs to the logs parameter.
        self.append_value_to_parameter("logs", "Checking for prompt driver..\n")

        prompt_driver = params.get("prompt_driver", None)

        if not prompt_driver:
            self.append_value_to_parameter(
                "logs", "Using GriptapeCloudPromptDriver as no prompt driver was provided.\n"
            )

            # Grab the appropriate parameters
            model = params.get("model", DEFAULT_MODEL)
            self.append_value_to_parameter("logs", f"Using model: {model}\n")

            prompt_driver = GriptapeCloudPromptDriver(
                model=model,
                api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR),
                stream=True,
            )
        else:
            self.append_value_to_parameter("logs", "Using provided prompt driver.\n")

        self.append_value_to_parameter("logs", "Creating agent..\n")
        agent = GtAgent(prompt_driver=prompt_driver)

        self.append_value_to_parameter("logs", "Agent created.\n")
        self.append_value_to_parameter("logs", "Getting prompt..\n")

        prompt = params.get("prompt", "")

        # Run the agent asynchronously
        self.append_value_to_parameter("logs", "Started processing agent..\n")
        yield lambda: self._process(agent, prompt)
        self.append_value_to_parameter("logs", "Finished processing agent.\n")

        try_throw_error(agent.output)

    def _process(self, agent: GtAgent, prompt: BaseArtifact | str) -> Structure:
        stream = Stream(agent)
        for artifact in stream.run(prompt):
            self.append_value_to_parameter(parameter_name="output", value=artifact.value)
        return agent
