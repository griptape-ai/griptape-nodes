from griptape.drivers.prompt.openai import OpenAiChatPromptDriver
from griptape_nodes.exe_types.core_types import ParameterUIOptions
from nodes.griptape_nodes_library.drivers.prompt.base_prompt_driver import BasePromptDriverNode

DEFAULT_MODEL = "gpt-4o"
MODELS=["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
API_KEY_ENV_VAR = "OPENAI_API_KEY"
SERVICE = "OpenAI"


class OpenAiPromptDriverNode(BasePromptDriverNode):
    """Node for OpenAi Prompt Driver.

    This node creates an OpenAi prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Set any defaults
        model_parameter = self.get_parameter_by_name("model")
        if model_parameter is not None:
            model_parameter.default_value = DEFAULT_MODEL
            model_parameter.input_types = ["str", "None"]
            model_parameter.ui_options = ParameterUIOptions(simple_dropdown_options=(ParameterUIOptions.SimpleDropdown(enum_choices=MODELS)))

        # Delete top_k because openai does not use it
        parameter = self.get_parameter_by_name("top_k")
        if parameter is not None:
            self.remove_parameter(parameter)

    def process(self) -> None:
        # Grab the API key

        # Get the parameters from the node
        params = self.parameter_values
        kwargs = {}
        kwargs["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)
        kwargs["model"] = params.get("model", DEFAULT_MODEL)
        response_format = params.get("response_format", None)
        seed = params.get("seed", None)
        stream = params.get("stream", False)
        temperature = params.get("temperature", None)
        use_native_tools = params.get("use_native_tools", False)
        max_tokens = params.get("max_tokens", -1)
        max_attempts = params.get("max_attempts_on_fail", None)
        top_p = None if params.get("min_p", None) is None else 1 - float(params["min_p"])

        if response_format == "json_object":
            response_format = {"type": "json_object"}
            kwargs["response_format"] = response_format
        if seed:
            kwargs["seed"] = seed
        if stream:
            kwargs["stream"] = stream
        if temperature:
            kwargs["temperature"] = temperature
        if max_attempts:
            kwargs["max_attempts"] = max_attempts
        if use_native_tools:
            kwargs["use_native_tools"] = use_native_tools
        if max_tokens > 0:
            kwargs["max_tokens"] = max_tokens

        kwargs["extra_params"] = {}
        if top_p:
            kwargs["extra_params"]["top_p"] = top_p

        # Create the driver
        driver = OpenAiChatPromptDriver(**kwargs)

        # Set the output
        self.parameter_output_values["driver"] = driver
