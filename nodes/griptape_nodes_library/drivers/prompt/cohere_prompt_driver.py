import cohere
from griptape.drivers.prompt.cohere import CoherePromptDriver as GtCoherePromptDriver

from griptape_nodes_library.drivers.prompt.base_prompt_driver import BasePromptDriver

DEFAULT_MODEL = "command-r-plus"
API_KEY_ENV_VAR = "COHERE_API_KEY"
SERVICE = "Cohere"


class CoherePrompt(BasePromptDriver):
    """Node for Cohere Prompt Driver.

    This node creates a Cohere prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Set any defaults
        model_parameter = self.get_parameter_by_name("model")
        if model_parameter is not None:
            model_parameter.default_value = DEFAULT_MODEL
            model_parameter.input_types = ["str"]

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # Initialize kwargs with required parameters
        kwargs = {}
        kwargs["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)
        kwargs["model"] = params.get("model", DEFAULT_MODEL)

        # Handle optional parameters
        max_attempts = params.get("max_attempts_on_fail", None)
        use_native_tools = params.get("use_native_tools", False)
        max_tokens = params.get("max_tokens", None)
        min_p = params.get("min_p", None)
        top_k = params.get("top_k", None)

        if max_attempts:
            kwargs["max_attempts"] = max_attempts
        if use_native_tools:
            kwargs["use_native_tools"] = use_native_tools
        if max_tokens is not None and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens
        if min_p is not None:
            kwargs["extra_params"] = {"p": 1 - min_p}
        if top_k:
            kwargs["extra_params"]["k"] = top_k

        self.parameter_output_values["prompt_driver"] = GtCoherePromptDriver(**kwargs)

    def validate_node(self) -> list[Exception] | None:
        # Items here are openai api key
        exceptions = []
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        try:
            co = cohere.Client(api_key)
            co.list_custom_models()
        except cohere.errors.UnauthorizedError as e:
            exceptions.append(e)
        return exceptions if exceptions else None
