from griptape.drivers.prompt.anthropic import AnthropicPromptDriver as GtAnthropicPromptDriver

from griptape_nodes.traits.options import Options
from griptape_nodes_library.misc.base_prompt_settings import BasePromptSettings

DEFAULT_MODEL = "claude-3-7-sonnet-latest"
MODELS = ["claude-3-7-sonnet-latest", "claude-3-5-sonnet-latest", "claude-3-5-opus-latest", "claude-3-5-haiku-latest"]
API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"
SERVICE = "Anthropic"

SUCCESS = 200


class AnthropicPromptModelSettings(BasePromptSettings):
    """Node for Anthropic Prompt Driver.

    This node creates an Anthropic prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Update the parameters

        # Update the list of models
        model_parameter = self.get_parameter_by_name("model")

        # Find the options trait
        if model_parameter:
            trait = model_parameter.find_element_by_id("Options")
            if trait and isinstance(trait, Options):
                # Update the choices in the trait
                trait.choices = MODELS
            model_parameter.default_value = DEFAULT_MODEL

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # Initialize kwargs with required parameters
        kwargs = {}
        kwargs["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)
        kwargs["model"] = params.get("model", DEFAULT_MODEL)

        # Handle optional parameters
        response_format = params.get("response_format", None)
        stream = params.get("stream", False)
        temperature = params.get("temperature", None)
        max_attempts = params.get("max_attempts_on_fail", None)
        use_native_tools = params.get("use_native_tools", False)
        max_tokens = params.get("max_tokens", None)
        top_p = None if params.get("min_p", None) is None else 1 - float(params["min_p"])
        min_p = params.get("min_p", None)
        top_k = params.get("top_k", None)

        if response_format == "json_object":
            response_format = {"type": "json_object"}
            kwargs["response_format"] = response_format
        if stream:
            kwargs["stream"] = stream
        if temperature:
            kwargs["temperature"] = temperature
        if max_attempts:
            kwargs["max_attempts"] = max_attempts
        if use_native_tools:
            kwargs["use_native_tools"] = use_native_tools
        if max_tokens is not None and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens

        kwargs["extra_params"] = {}
        if min_p:
            kwargs["top_p"] = 1 - min_p  # min_p -> top_p
        if top_k:
            kwargs["top_k"] = top_k

        # Create the driver
        driver = GtAnthropicPromptDriver(**kwargs)

        # Set the output
        self.parameter_output_values["prompt model settings"] = driver

    def validate_node(self) -> list[Exception] | None:
        # Items here are openai api key
        exceptions = []
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions

        return exceptions if exceptions else None
