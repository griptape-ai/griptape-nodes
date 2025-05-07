"""Defines the AnthropicPrompt node for configuring the Anthropic Prompt Driver.

This module provides the `AnthropicPrompt` class, which allows users
to configure and utilize the Anthropic prompt service within the Griptape
Nodes framework. It inherits common prompt parameters from `BasePrompt`, sets
Cohere specific model options, requires a Cohere API key via
node configuration, and instantiates the `GtCoherePromptDriver`.
"""

from griptape.drivers.prompt.cohere import CoherePromptDriver as GtCoherePromptDriver

from griptape_nodes_library.config.prompt.base_prompt import BasePrompt

# --- Constants ---

SERVICE = "Cohere"
API_KEY_URL = "https://dashboard.cohere.com/api-keys"
API_KEY_ENV_VAR = "COHERE_API_KEY"
MODEL_CHOICES = ["command-r-plus"]
DEFAULT_MODEL = MODEL_CHOICES[0]


class CoherePrompt(BasePrompt):
    """Node for configuring and providing a Cohere Prompt Driver.

    Inherits from `BasePrompt` to leverage common LLM parameters. This node
    customizes the available models to those supported by Cohere, requires a
    Cohere API key set in the node's configuration under the 'Cohere' service, and potentially handles parameter conversions specific to the
    Cohere driver (like min_p to top_p).

    The `process` method uses the `_get_common_driver_args` helper, adds
    Cohere-specific configurations, and instantiates the
    `CoherePromptDriver`.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the CoherePrompt node.

        Calls the superclass initializer, then modifies the inherited 'model'
        parameter to use Anthropic specific models and sets a default.
        """
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for Anthropic specifics.
        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)

        # Replace `min_p` with `top_p` for Cohere.
        self._replace_param_by_name(
            param_name="min_p", new_param_name="p", tooltip=None, default_value=0.9, ui_options=None
        )
        self._replace_param_by_name(param_name="top_k", new_param_name="k")

        # Remove the 'seed' parameter as it's not directly used by Cohere.
        self.remove_parameter_by_name("seed")
        self.remove_parameter_by_name("response_format")

    def process(self) -> None:
        """Processes the node configuration to create a CoherePromptDriver.

        Retrieves parameter values, uses the `_get_common_driver_args` helper
        for common settings, then adds Cohere-specific arguments like API key
        and model. Handles the conversion of `min_p` to `p` if `p` is set. Handles
        the conversion of `top_k` to `k` if `k` is set.
        Finally, instantiates the `CoherePromptDriver` and assigns it to the
        'prompt_model_config' output parameter.

        Raises:
            KeyError: If the Cohere API key is not found in the node configuration.
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

        # Handle parameters that go into 'extra_params' for Griptape Cloud.
        extra_params = {}

        extra_params["p"] = self.get_parameter_value("p")
        extra_params["k"] = self.get_parameter_value("k")

        if extra_params:
            specific_args["extra_params"] = extra_params

        # --- Combine Arguments and Instantiate Driver ---
        # Combine common arguments (potentially modified) with Cohere specific arguments.
        all_kwargs = {**common_args, **specific_args}

        # Create the Cohere prompt driver instance.
        driver = GtCoherePromptDriver(**all_kwargs)

        # Set the output parameter 'prompt_model_config'.
        self.parameter_output_values["prompt_model_config"] = driver

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validates that the Cohere API key is configured correctly.

        Calls the base class helper `_validate_api_key` with Cohere-specific
        configuration details.
        """
        return self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=API_KEY_ENV_VAR,
            api_key_url=API_KEY_URL,
        )
