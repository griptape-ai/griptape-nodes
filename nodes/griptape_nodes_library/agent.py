from typing import Any

from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.structures import Agent
from griptape.utils import Stream

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterDictionary,
    ParameterGroup,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode, ControlNode
from griptape_nodes.traits.button import Button
from griptape_nodes.traits.options import Options
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
        self.add_parameter(
            ParameterDictionary(
                name="context",
                type="[str, str]",
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
                traits={Options(["gpt-4o", "gpt-3.5", "gpt-4"])},
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
                ui_options={"multiline": True},
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
            ParameterList(
                name="tool_list",
                input_types=[
                    "Tool"
                ],  # We only need to specify the element type; the container will automatically accept list[Tool], too.
                output_type="Tool",  # Same
                type="Tool",  # Same
                default_value=None,
                tooltip="All of the tools",
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
                traits={Button(button_type="modal")},
                ui_options={"multiline": True, "placeholder_text": "The Agent Response"},
            )
        self.add_node_element(tools_group)

        # Do some ParameterList magick
        tool_list = self.get_parameter_by_name("tool_list")
        if isinstance(tool_list, ParameterList):
            entry_0 = tool_list.add_child_parameter()
            entry_1 = tool_list.add_child_parameter()
            print(entry_0.name)
            print(tool_list[1].name)

        # Now with ParameterDictionary
        context = self.get_parameter_by_name("context")
        if isinstance(context, ParameterDictionary):
            kvp_0 = context.add_key_value_pair()
            kvp_1 = context.add_key_value_pair()
            kvp_0.set_key("first_name")
            kvp_0.set_value("James")

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

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        driver_type = str(type(value).__name__).lower()
        self.handle_prompt_driver(parameter, driver_type, modified_parameters_set)

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        node_class = source_node.__class__.__name__.lower()
        self.handle_prompt_driver(target_parameter, node_class)

    def select_choices(self, value: str) -> list[str]:
        match value:
            case _ if "anthropic" in value:
                return [
                    "claude-3-opus",
                    "claude-3-sonnet-latest",
                    "claude-3-haiku",
                    "claude-3-5-sonnet",
                ]
            case _ if "openai" in value:
                return ["gpt-4-turbo", "gpt-4-1106-preview", "gpt-4", "gpt-3.5-turbo"]
            case _ if "ollama" in value:
                return ["llama3", "llama2", "mistral", "mpt"]
        return []

    def handle_prompt_driver(
        self, parameter: Parameter, type_string: Any, modified_parameters_set: set[str] | None = None
    ) -> None:
        if parameter.name == "prompt_driver":
            prompt_model = self.get_parameter_by_name("prompt_model")
            if prompt_model:
                trait = prompt_model.find_element_by_id("Options")
                if trait and isinstance(trait, Options):
                    if modified_parameters_set:
                        modified_parameters_set.add("prompt_model")
                    choices = self.select_choices(type_string)
                    if choices:
                        trait.choices = choices
                    self.set_parameter_value("prompt_model", self.get_parameter_value("prompt_model"))

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
