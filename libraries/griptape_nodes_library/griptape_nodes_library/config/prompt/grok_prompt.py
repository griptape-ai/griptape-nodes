"""Defines the GrokPrompt node for configuring the Grok Prompt Driver.

This module provides the `GrokPrompt` class, which allows users
to configure and utilize the Grok prompt service within the Griptape
Nodes framework. It inherits common prompt parameters from `BasePrompt`, sets
Grok specific model options, requires a Grok API key via
node configuration, and instantiates the `GrokPromptDriver`.
"""

from griptape.drivers.prompt.grok import GrokPromptDriver as GtGrokPromptDriver

from griptape_nodes_library.config.prompt.base_prompt import BasePrompt

# --- Constants ---

SERVICE = "Grok"
API_KEY_URL = "https://console.x.ai"
API_KEY_ENV_VAR = "GROK_API_KEY"
MODEL_CHOICES = ["grok-3-beta", "grok-3-fast-beta", "grok-3-mini-beta", "grok-3-mini-fast-beta", "grok-2-vision-1212"]
DEFAULT_MODEL = MODEL_CHOICES[0]


class GrokPrompt(BasePrompt):
    """Node for configuring and providing a Grok  Prompt Driver.

    Inherits from `BasePrompt` to leverage common LLM parameters. This node
    customizes the available models to those supported by Grok,
    removes parameters not applicable to Grok (like 'seed'), and
    requires a Grok API key to be set in the node's configuration
    under the 'Grok' service.

    The `process` method gathers the configured parameters and the API key,
    utilizes the `_get_common_driver_args` helper from `BasePrompt`, adds
    Grok specific configurations, then instantiates a
    `GrokPromptDriver` and assigns it to the 'prompt_model_config'
    output parameter.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the GrokPrompt node.

        Calls the superclass initializer, then modifies the inherited 'model'
        parameter to use Grok specific models and sets a default.
        It also removes the 'seed' parameter inherited from `BasePrompt` as it's
        not directly supported by the Grok driver implementation.
        """
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for Grok specifics.
        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)

        # Remove `top_k` parameter as it's not used by Grok.
        self.remove_parameter_by_name("seed")
        self.remove_parameter_by_name("top_k")

        # Replace `min_p` with `top_p` for Grok.
        self._replace_param_by_name(param_name="min_p", new_param_name="top_p", default_value=0.9)

    def process(self) -> None:
        """Processes the node configuration to create a GrokPromptDriver.

        Retrieves parameter values set on the node and the required API key from
        the node's configuration system. It constructs the arguments dictionary
        for the `GrokPromptDriver`, handles optional parameters and
        any necessary conversions (like 'min_p' to 'top_p'), instantiates the
        driver, and assigns it to the 'prompt_model_config' output parameter.

        Raises:
            KeyError: If the Grok API key is not found in the node configuration
                      (though `validate_before_workflow_run` should prevent this during execution).
        """
        # Retrieve all parameter values set on the node UI or via input connections.
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BasePrompt to get args like temperature, stream, max_attempts, etc.
        common_args = self._get_common_driver_args(params)

        # --- Prepare Grok Specific Arguments ---
        specific_args = {}

        # Retrieve the mandatory API key.
        specific_args["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)

        # Get the selected model.
        specific_args["model"] = self.get_parameter_value("model")

        # Handle parameters that go into 'extra_params' for Grok.
        extra_params = {}

        extra_params["top_p"] = self.get_parameter_value("top_p")

        # Assign extra_params if not empty
        if extra_params:
            specific_args["extra_params"] = extra_params

        # --- Combine Arguments and Instantiate Driver ---
        # Combine common arguments with Grok specific arguments.
        # Specific args take precedence if there's an overlap (though unlikely here).
        all_kwargs = {**common_args, **specific_args}

        # Create the Grok prompt driver instance.
        driver = GtGrokPromptDriver(**all_kwargs)

        # Set the output parameter 'prompt_model_config'.
        self.parameter_output_values["prompt_model_config"] = driver

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validates that the Grok API key is configured correctly.

        Calls the base class helper `_validate_api_key` with Grok-specific
        configuration details.
        """
        return self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=API_KEY_ENV_VAR,
            api_key_url=API_KEY_URL,
        )
