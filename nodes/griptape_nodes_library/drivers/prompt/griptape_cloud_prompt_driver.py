from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver as GtGriptapeCloudPromptDriver

from griptape_nodes.traits.options import Options
from griptape_nodes_library.drivers.prompt.base_prompt_driver import BasePromptDriver

DEFAULT_MODEL = "gpt-4o"
MODELS = ["gpt-4o"]
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
SUCCESS = 200


class GriptapeCloudPromptDriver(BasePromptDriver):
    """Node for Griptape Cloud Prompt Driver.

    This node creates a Griptape Cloud prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Set any defaults
        model_parameter = self.get_parameter_by_name("model")
        if model_parameter is not None:
            model_parameter.default_value = DEFAULT_MODEL
            model_parameter.input_types = ["str"]
            model_parameter.add_trait(Options(choices=MODELS))

        seed_parameter = self.get_parameter_by_name("seed")
        if seed_parameter is not None:
            self.remove_parameter(seed_parameter)

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
        if top_p:
            kwargs["extra_params"]["top_p"] = top_p

        # Create the driver
        driver = GtGriptapeCloudPromptDriver(**kwargs)

        # Set the output
        self.parameter_output_values["prompt_driver"] = driver

    def validate_node(self) -> list[Exception] | None:
        # Items here are openai api key
        exceptions = []
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions

        return exceptions if exceptions else None
