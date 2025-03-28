import anthropic
from griptape.drivers.prompt.anthropic import AnthropicPromptDriver
from rich import print

from griptape_nodes_library.drivers.base_prompt_driver import gnBasePromptDriver
from griptape_nodes_library.utils.env_utils import getenv

DEFAULT_MODEL = "claude-3-5-sonnet-latest"
API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"
SERVICE = "Anthropic"


class gnAnthropicPromptDriver(gnBasePromptDriver):
    """Node for Anthropic Prompt Driver.

    This node creates an Anthropic prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Set any defaults
        self.parameter_values["model"] = DEFAULT_MODEL

        # Remove parameters not used by Azure OpenAI

    def process(self) -> None:
        # Get the parameters from the node

        # Initialize kwargs with required parameters
        kwargs = {}
        kwargs["api_key"] = getenv(service=SERVICE, value=API_KEY_ENV_VAR)
        kwargs["model"] = self.valid_or_fallback("model", DEFAULT_MODEL)

        # Handle optional parameters
        stream = self.valid_or_fallback("stream", False)
        temperature = self.valid_or_fallback("temperature", None)
        max_attempts = self.valid_or_fallback("max_attempts_on_fail", None)
        use_native_tools = self.valid_or_fallback("use_native_tools", False)
        max_tokens = self.valid_or_fallback("max_tokens", None)
        min_p = self.valid_or_fallback("min_p", None)
        top_k = self.valid_or_fallback("top_k", None)

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

        print("\n\nANTHROPIC PROMPT DRIVER:")
        print(kwargs)
        print("\n\n")

        self.parameter_output_values["driver"] = AnthropicPromptDriver(**kwargs)

    def validate_node(self) -> list[Exception] | None:
        exceptions = []
        api_key = getenv(SERVICE, API_KEY_ENV_VAR)
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
