"""Defines the GooglePrompt node for configuring the Google Prompt Driver.

This module provides the `GooglePrompt` class, which allows users
to configure and utilize the Google (Gemini) prompt service within the Griptape
Nodes framework. It inherits common prompt parameters from `BasePrompt`, sets
Google-specific model options, requires a Google API key via
node configuration, and instantiates the `GooglePromptDriver`.
"""

from griptape.drivers.prompt.google import GooglePromptDriver as GtGooglePromptDriver

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes_library.config.prompt.base_prompt import BasePrompt

# --- Constants ---

SERVICE = "Google"
API_KEY_URL = "https://aistudio.google.com/apikey"
API_KEY_ENV_VAR = "GOOGLE_API_KEY"
MODEL_CHOICES = [
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]
DEFAULT_MODEL = MODEL_CHOICES[0]


class GooglePrompt(BasePrompt):
    """Node for configuring and providing a Google Prompt Driver.

    Inherits from `BasePrompt` to leverage common LLM parameters. This node
    customizes the available models to those supported by Google (Gemini),
    requires a Google API key set in the node's configuration under the
    'Google' service, and handles parameter conversions specific to the
    Google driver (like min_p to top_p).

    The `process` method uses the `_get_common_driver_args` helper, adds
    Google-specific configurations, and instantiates the
    `GooglePromptDriver`.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the GooglePrompt node.

        Calls the superclass initializer, then modifies the inherited 'model'
        parameter to use Google Gemini models and sets a default.
        """
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for Google Gemini specifics.
        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)

        # Replace `min_p` with `top_p` for Google.
        self._replace_param_by_name(
            param_name="min_p", new_param_name="top_p", tooltip=None, default_value=0.9, ui_options=None
        )

        # Remove the 'seed' parameter as it's not supported by GooglePromptDriver.
        self.remove_parameter_element_by_name("seed")

    def process(self) -> None:
        """Processes the node configuration to create a GooglePromptDriver.

        Retrieves parameter values, uses the `_get_common_driver_args` helper
        for common settings, then adds Google-specific arguments like API key,
        model, top_p, and top_k. Instantiates the `GooglePromptDriver` and
        assigns it to the 'prompt_model_config' output parameter.

        Raises:
            KeyError: If the Google API key is not found in the node configuration.
        """
        # Retrieve all parameter values set on the node.
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BasePrompt. This gets temperature, stream,
        # max_attempts, max_tokens, use_native_tools, top_k if they are set.
        common_args = self._get_common_driver_args(params)

        # --- Prepare Google Specific Arguments ---
        specific_args = {}

        # Retrieve the mandatory API key.
        specific_args["api_key"] = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)

        # Get the selected model.
        specific_args["model"] = self.get_parameter_value("model")

        # Google driver uses top_p and top_k directly as kwargs.
        specific_args["top_p"] = self.get_parameter_value("top_p")
        specific_args["top_k"] = self.get_parameter_value("top_k")

        # --- Combine Arguments and Instantiate Driver ---
        # Combine common arguments with Google specific arguments.
        all_kwargs = {**common_args, **specific_args}

        # Create the Google prompt driver instance.
        driver = GtGooglePromptDriver(**all_kwargs)

        # Set the output parameter 'prompt_model_config'.
        self.parameter_output_values["prompt_model_config"] = driver

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validates that the Google API key is configured correctly.

        Calls the base class helper `_validate_api_key` with Google-specific
        configuration details.
        """
        return self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=API_KEY_ENV_VAR,
            api_key_url=API_KEY_URL,
        )
