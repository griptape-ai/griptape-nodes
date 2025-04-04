from griptape.drivers.prompt.azure_openai_chat_prompt_driver import AzureOpenAiChatPromptDriver

from nodes.griptape_nodes_library.drivers.prompt.base_prompt_driver import BasePromptDriverNode

# Available models
# "gpt-4o", "gpt-4", "gpt-3.5-turbo-16k", "gpt-3.5-turbo"
DEFAULT_MODEL = "gpt-4o"
DEFAULT_DEPLOYMENT = "gpt-4o"
DEFAULT_AZURE_ENDPOINT_ENV_VAR = "AZURE_OPENAI_ENDPOINT"
API_KEY_ENV_VAR = "AZURE_OPENAI_API_KEY"
SERVICE = "Microsoft Azure"


class AzureOpenAiChatPromptDriverNode(BasePromptDriverNode):
    """Node for Azure OpenAI Chat Prompt Driver.

    This node creates an Azure OpenAI chat prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Remove parameters not used by Azure OpenAI
        param = self.get_parameter_by_name("min_p")
        if param is not None:
            self.remove_parameter(param)

        param = self.get_parameter_by_name("top_k")
        if param is None:
            msg = "top_k is not a valid parameter for Azure OpenAI."
            raise ValueError(msg)
        self.remove_parameter(param)

    def process(self) -> None:
        # Initialize kwargs with required parameters
        kwargs = {}
        kwargs["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)
        kwargs["azure_endpoint"] = self.get_config_value(service=SERVICE, value=DEFAULT_AZURE_ENDPOINT_ENV_VAR)

        kwargs["model"] = self.valid_or_fallback("model", DEFAULT_MODEL)
        # HACKATTACK:
        kwargs["azure_deployment"] = DEFAULT_DEPLOYMENT

        # Handle optional parameters
        response_format = self.valid_or_fallback("response_format", None)
        seed = self.valid_or_fallback("seed", None)
        temperature = self.valid_or_fallback("temperature", None)
        max_attempts = self.valid_or_fallback("max_attempts_on_fail", None)
        use_native_tools = self.valid_or_fallback("use_native_tools", False)
        max_tokens = self.valid_or_fallback("max_tokens", None)

        # Apply optional parameters if they exist
        if response_format == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        if seed:
            kwargs["seed"] = seed
        if temperature:
            kwargs["temperature"] = temperature
        if max_attempts:
            kwargs["max_attempts"] = max_attempts
        if use_native_tools:
            kwargs["use_native_tools"] = use_native_tools
        if max_tokens is not None and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens

        # Set the output
        self.parameter_output_values["driver"] = AzureOpenAiChatPromptDriver(**kwargs)

    def validate_node(self) -> list[Exception] | None:
        return super().validate_node()
