from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.structures import Agent
from griptape.utils import Stream

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterUIOptions
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes_library.utils.error_utils import try_throw_error

DEFAULT_MODEL = "gpt-4o"
SERVICE = "Griptape"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"


class SimpleAgentNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.category = "Agent"
        self.description = "Run a previous agent"
        self.add_parameter(
            Parameter(
                name="agent",
                type="Agent",
                input_types=["Agent", "dict"],
                output_type="Agent",
                tooltip="",
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value="",
                tooltip="",
                ui_options=ParameterUIOptions(
                    string_type_options=ParameterUIOptions.StringType(
                        multiline=True,
                    )
                ),
            )
        )

        self.add_parameter(
            Parameter(
                name="output",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value="",
                tooltip="What the agent said.",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options=ParameterUIOptions(
                    string_type_options=ParameterUIOptions.StringType(
                        multiline=True,
                        placeholder_text="The agent response",
                    )
                ),
            )
        )

    # Same here as RunAgentNode. TODO(kate):package into one
    def validate_node(self) -> list[Exception] | None:
        # Items here are openai api key
        exceptions = []
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        return exceptions if exceptions else None

    def process(self) -> None:
        # Get input values
        params = self.parameter_values

        agent = params.get("agent", None)
        if not agent:
            agent = Agent(
                prompt_driver=GriptapeCloudPromptDriver(
                    api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR), stream=True
                )
            )

        prompt = params.get("prompt", None)
        if prompt:
            # Run the agent
            full_output = ""
            for artifact in Stream(agent).run(prompt):
                full_output += artifact.value
            self.parameter_output_values["output"] = full_output
        else:
            self.parameter_output_values["output"] = "Agent Created"

        self.parameter_output_values["agent"] = agent
        try_throw_error(agent.output)
