from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.structures import Agent
from griptape.utils import Stream

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterGroup,
    ParameterMode,
    ParameterUIOptions,
)
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes_library.utils.error_utils import try_throw_error

DEFAULT_MODEL = "gpt-4o"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"


class RunAgentNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.category = "Agent"
        self.description = "Create an agent and run it."

        self.add_parameter(
            Parameter(
                name="agent",
                input_types=["Agent", "dict"],
                output_type="Agent",
                tooltip="",
            )
        )
        with ParameterGroup(group_name="Agent Config") as config_group:
            Parameter(
                name="prompt_driver",
                input_types=["Prompt Driver"],
                output_type="Prompt Driver",
                type="Prompt Driver",
                default_value=None,
                tooltip="",
            )
            Parameter(
                name="prompt_model",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value=DEFAULT_MODEL,
                tooltip="",
            )
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
        self.add_node_element(config_group)

        with ParameterGroup(group_name="Agent Tools") as tools_group:
            Parameter(
                name="tool",
                input_types=["Tool"],
                output_type="Tool",
                type="Tool",
                default_value=None,
                tooltip="",
            )
            Parameter(
                name="tool_list",
                input_types=["list[Tool]"],
                output_type="list[Tool]",
                type="list[Tool]",
                default_value=None,
                tooltip="",
            )
            Parameter(
                name="ruleset",
                input_types=["Ruleset"],
                output_type="Ruleset",
                type="Ruleset",
                tooltip="",
            )
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
        self.add_node_element(tools_group)

    # Only requires a valid GT_CLOUD_API_KEY
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
        # Get api key
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)

        # Get input values
        params = self.parameter_values

        kwargs = {}

        # Create the Prompt Driver
        model = self.valid_or_fallback("prompt_model", DEFAULT_MODEL)

        kwargs["prompt_driver"] = self.valid_or_fallback(
            "prompt_driver", GriptapeCloudPromptDriver(model=model, stream=True, api_key=api_key)
        )
        agent = params.get("agent", None)
        if not agent:
            # Get any tools
            tool = params.get("tool", None)
            tools = params.get("tools", None)
            agent_tools = [tool] if tool else []
            agent_tools += tools if tools else []
            if agent_tools:
                kwargs["tools"] = agent_tools

            # Get any rules
            ruleset = self.valid_or_fallback("ruleset", None)
            if ruleset:
                kwargs["rulesets"] = [ruleset]

            # Create the Agent
            agent = Agent(**kwargs)

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
