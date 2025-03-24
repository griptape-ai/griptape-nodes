from griptape.drivers.prompt.cohere import CoherePromptDriver

from griptape_nodes_library.drivers.base_prompt_driver import gnBasePromptDriver

DEFAULT_MODEL = "command-r-plus"
API_KEY_ENV_VAR = "COHERE_API_KEY"
SERVICE = "Cohere"


class gnCoherePromptDriver(gnBasePromptDriver):
    """Node for Cohere Prompt Driver.

    This node creates a Cohere prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # Initialize kwargs with required parameters
        kwargs = {}
        kwargs["api_key"] = self.getenv(service=SERVICE, value=API_KEY_ENV_VAR)
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

        self.parameter_output_values["driver"] = CoherePromptDriver(**kwargs)


if __name__ == "__main__":
    drv = gnCoherePromptDriver(name="simpleClear")
    drv.process()
