"""Defines the GriptapeCloudPrompt node for configuring the Griptape Cloud Prompt Driver.

This module provides the `GriptapeCloudPrompt` class, which allows users
to configure and utilize the Griptape Cloud prompt service within the Griptape
Nodes framework. It inherits common prompt parameters from `BasePrompt`, sets
Griptape Cloud specific model options, requires a Griptape Cloud API key via
node configuration, and instantiates the `GriptapeCloudPromptDriver`.
"""

from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver as GtGriptapeCloudPromptDriver

from griptape_nodes.traits.options import Options
from griptape_nodes_library.misc.base_prompt import BasePrompt

# --- Constants ---

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
DEFAULT_MODEL = "gpt-4.1-mini"
MODELS = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4.5-preview",
    "o1",
    "o1-mini",
    "o3-mini",
    "other",
]  # currently only gpt-4o is supported


class ExGriptapeCloudPrompt(BasePrompt):
    """Node for Griptape Cloud Prompt .

    This node creates a Griptape Cloud prompt driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the ExGriptapeCloudPrompt node.

        Calls the superclass initializer, then modifies the inherited 'model'
        parameter to use Griptape Cloud specific models and sets a default.
        It also removes the 'seed' parameter inherited from `BasePrompt` as it's
        not directly supported by the Griptape Cloud driver implementation.
        """
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for Griptape Cloud specifics.
        model_parameter = self.get_parameter_by_name("model")

        # Find the options trait
        if model_parameter:
            trait = model_parameter.find_element_by_id("Options")
            if trait and isinstance(trait, Options):
                trait.choices = MODELS
            model_parameter.default_value = DEFAULT_MODEL

        # Remove the 'seed' parameter as it's not directly used by GriptapeCloudPromptDriver.
        seed_parameter = self.get_parameter_by_name("seed")
        if seed_parameter is not None:
            self.remove_parameter(seed_parameter)

    def process(self) -> None:
        """Processes the node configuration to create a GriptapeCloudPromptDriver.

        Retrieves parameter values set on the node and the required API key from
        the node's configuration system. It constructs the arguments dictionary
        for the `GriptapeCloudPromptDriver`, handles optional parameters and
        any necessary conversions (like 'min_p' to 'top_p'), instantiates the
        driver, and assigns it to the 'prompt model config' output parameter.

        Raises:
            KeyError: If the Griptape Cloud API key is not found in the node configuration
                      (though `validate_node` should prevent this during execution).
        """
        # Retrieve all parameter values set on the node UI or via input connections.
        params = self.parameter_values

        # --- Prepare Driver Arguments ---
        # Initialize kwargs dictionary for the driver constructor.
        kwargs = {}

        # Retrieve the mandatory API key from the node's configuration.
        # This raises KeyError if not found, handled by the execution environment or validate_node.
        kwargs["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)

        # Get the selected model, using the default if not specified.
        kwargs["model"] = params.get("model", DEFAULT_MODEL)

        # --- Handle Optional Driver Parameters ---
        # Retrieve optional parameters if they have been set (non-default value or connected).
        response_format = params.get("response_format", None)
        stream = params.get("stream", False)
        temperature = params.get("temperature", None)
        max_attempts = params.get("max_attempts_on_fail", None)
        use_native_tools = params.get("use_native_tools", False)
        max_tokens = params.get("max_tokens", None)

        # Convert 'min_p' (from BasePrompt) to 'top_p' if provided, as Griptape Cloud uses top_p.
        min_p_value = params.get("min_p", None)
        top_p = None
        if min_p_value is not None:
            # Ensure conversion handles potential float precision issues if necessary.
            # Note: Standard top_p is usually directly set, min_p interpretation might vary.
            # This assumes 1 - min_p is the intended conversion to top_p.
            top_p = 1.0 - float(min_p_value)

        # Add optional parameters to kwargs only if they are set.
        # The driver itself usually handles defaults if a parameter is not provided (is None).
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

        # Handle parameters that go into 'extra_params' for Griptape Cloud.
        kwargs["extra_params"] = {}
        if top_p:
            kwargs["extra_params"]["top_p"] = top_p

        # Remove extra_params if empty to avoid sending empty dict.
        if not kwargs["extra_params"]:
            del kwargs["extra_params"]

        # --- Instantiate and Output Driver ---
        # Create the Griptape Cloud prompt driver instance with the prepared arguments.
        driver = GtGriptapeCloudPromptDriver(**kwargs)

        # Set the output parameter 'prompt model config' with the created driver instance.
        self.parameter_output_values["prompt model config"] = driver

    def validate_node(self) -> list[Exception] | None:
        """Performs pre-run validation checks for the node configuration.

        Specifically checks if the Griptape Cloud API key (`GT_CLOUD_API_KEY`)
        is defined within the node's configuration under the 'Griptape' service.

        Returns:
            A list containing a KeyError if the API key is missing, otherwise None.
        """
        exceptions = []
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions

        return exceptions if exceptions else None
