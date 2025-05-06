"""Defines the AnthropicPrompt node for configuring the Anthropic Prompt Driver.

This module provides the `AnthropicPrompt` class, which allows users
to configure and utilize the Anthropic prompt service within the Griptape
Nodes framework. It inherits common prompt parameters from `BasePrompt`, sets
Anthropic specific model options, requires an Anthropic API key via
node configuration, and instantiates the `GtAnthropicPromptDriver`.
"""

from griptape.drivers.prompt.anthropic import AnthropicPromptDriver as GtAnthropicPromptDriver

from griptape_nodes_library.config.prompt.base_prompt import BasePrompt

# --- Constants ---

SERVICE = "Anthropic"
API_KEY_URL = "https://console.anthropic.com/settings/keys"
API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"
MODEL_CHOICES = [
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet-latest",
    "claude-3-5-opus-latest",
    "claude-3-5-haiku-latest",
]
DEFAULT_MODEL = MODEL_CHOICES[0]


class AnthropicPrompt(BasePrompt):
    """Node for configuring and providing an Anthropic Prompt Driver.

    Inherits from `BasePrompt` to leverage common LLM parameters. This node
    customizes the available models to those supported by Anthropic, requires an
    Anthropic API key set in the node's configuration under the 'Anthropic'
    service, and potentially handles parameter conversions specific to the
    Anthropic driver (like min_p to top_p).

    The `process` method uses the `_get_common_driver_args` helper, adds
    Anthropic-specific configurations, and instantiates the
    `AnthropicPromptDriver`.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the AnthropicPrompt node.

        Calls the superclass initializer, then modifies the inherited 'model'
        parameter to use Anthropic specific models and sets a default.
        """
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for Anthropic specifics.
        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)

        # Replace `min_p` with `top_p` for Anthropic.
        self._replace_param_by_name(
            param_name="min_p", new_param_name="top_p", tooltip=None, default_value=0.9, ui_options=None
        )

        # Remove the 'seed' parameter as it's not directly used by GriptapeCloudPromptDriver.
        self.remove_parameter_by_name("seed")

    def process(self) -> None:
        """Processes the node configuration to create an AnthropicPromptDriver.

        Retrieves parameter values, uses the `_get_common_driver_args` helper
        for common settings, then adds Anthropic-specific arguments like API key
        and model. Handles the conversion of `min_p` to `top_p` if `min_p` is set.
        Finally, instantiates the `AnthropicPromptDriver` and assigns it to the
        'prompt_model_config' output parameter.

        Raises:
            KeyError: If the Anthropic API key is not found in the node configuration.
        """
        # Retrieve all parameter values set on the node.
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BasePrompt. This gets temperature, stream,
        # max_attempts, max_tokens, use_native_tools, min_p, top_k if they are set.
        common_args = self._get_common_driver_args(params)

        # --- Prepare Anthropic Specific Arguments ---
        specific_args = {}

        # Retrieve the mandatory API key.
        specific_args["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)

        # Get the selected model.
        specific_args["model"] = self.get_parameter_value("model")

        # Handle specific parameter conversions/logic for Anthropic driver
        # Anthropic uses 'top_p' and 'top_k' directly as kwargs.
        specific_args["top_p"] = self.get_parameter_value("top_p")

        response_format = self.get_parameter_value("response_format")
        if response_format == "json_object":
            response_format = {"type": "json_object"}
            specific_args["response_format"] = response_format

        # --- Combine Arguments and Instantiate Driver ---
        # Combine common arguments (potentially modified) with Anthropic specific arguments.
        all_kwargs = {**common_args, **specific_args}

        # Create the Anthropic prompt driver instance.
        driver = GtAnthropicPromptDriver(**all_kwargs)

        # Set the output parameter 'prompt_model_config'.
        self.parameter_output_values["prompt_model_config"] = driver

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validates that the Anthropic API key is configured correctly.

        Calls the base class helper `_validate_api_key` with Anthropic-specific
        configuration details.
        """
        return self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=API_KEY_ENV_VAR,
            api_key_url=API_KEY_URL,
        )
