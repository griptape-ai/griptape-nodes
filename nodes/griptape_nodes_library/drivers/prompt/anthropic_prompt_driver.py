import anthropic
from griptape.drivers.prompt.anthropic import AnthropicPromptDriver

from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.drivers.prompt.base_prompt_driver import BasePromptDriverNode
from traits.options import Options

DEFAULT_MODEL = "claude-3-7-sonnet-latest"
MODELS = ["claude-3-7-sonnet-latest", "claude-3-5-sonnet-latest", "claude-3-5-opus-latest", "claude-3-5-haiku-latest"]
API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"
SERVICE = "Anthropic"


class AnthropicPromptDriverNode(BasePromptDriverNode):
    """Node for Anthropic Prompt Driver.

    This node creates an Anthropic prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Set any defaults
        model_parameter = self.get_parameter_by_name("model")
        if model_parameter is not None:
            model_parameter.default_value = DEFAULT_MODEL
            model_parameter.add_trait(Options(choices=MODELS))

        # Remove parameters not used by Azure OpenAI

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # Initialize kwargs with required parameters
        kwargs = {}
        kwargs["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)
        kwargs["model"] = self.valid_or_fallback("model", DEFAULT_MODEL)

        # Handle optional parameters
        stream = params.get("stream", False)
        temperature = params.get("temperature", None)
        use_native_tools = params.get("use_native_tools", False)
        max_tokens = params.get("max_tokens", -1)
        max_attempts = params.get("max_attempts_on_fail", None)
        min_p = params.get("min_p", None)
        top_k = params.get("top_k", None)

        if stream:
            kwargs["stream"] = stream
        if temperature:
            kwargs["temperature"] = temperature
        if max_attempts:
            kwargs["max_attempts"] = max_attempts
        if use_native_tools:
            kwargs["use_native_tools"] = use_native_tools
        if min_p:
            kwargs["top_p"] = 1 - min_p  # min_p -> top_p
        if top_k:
            kwargs["top_k"] = top_k

        if max_tokens is not None and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens

        # Debug output
        debug_msg = "\n\nANTHROPIC PROMPT DRIVER:\n" + str(kwargs) + "\n\n"
        logger.debug(debug_msg)

        self.parameter_output_values["prompt_driver"] = AnthropicPromptDriver(**kwargs)

    def validate_node(self) -> list[Exception] | None:
        exceptions = []
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        try:
            client = anthropic.Anthropic(api_key=api_key)
            client.models.list()
        except anthropic.APIError as e:
            exceptions.append(e)
        return exceptions if exceptions else None
