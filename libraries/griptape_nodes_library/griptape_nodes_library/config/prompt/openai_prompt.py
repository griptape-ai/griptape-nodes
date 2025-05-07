"""Defines the OpenAiPrompt node for configuring the OpenAi Prompt Driver.

This module provides the `OpenAiPrompt` class, which allows users
to configure and utilize the OpenAi prompt service within the Griptape
Nodes framework. It inherits common prompt parameters from `BasePrompt`, sets
OpenAi specific model options, requires a OpenAi API key via
node configuration, and instantiates the `OpenAiPromptDriver`.
"""

from griptape.drivers.prompt.openai import OpenAiChatPromptDriver as GtOpenAiChatPromptDriver

from griptape_nodes_library.config.prompt.base_prompt import BasePrompt

# --- Constants ---

SERVICE = "OpenAI"
API_KEY_URL = "https://platform.openai.com/api-keys"
API_KEY_ENV_VAR = "OPENAI_API_KEY"
MODEL_CHOICES = ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4.5-preview", "o1", "o1-mini", "o3-mini"]
DEFAULT_MODEL = MODEL_CHOICES[0]


class OpenAiPrompt(BasePrompt):
    """Node for configuring and providing a OpenAi Chat Prompt Driver.

    Inherits from `BasePrompt` to leverage common LLM parameters. This node
    customizes the available models to those supported by OpenAi,
    removes parameters not applicable to OpenAi (like 'seed'), and
    requires a OpenAi API key to be set in the node's configuration
    under the 'OpenAi' service.

    The `process` method gathers the configured parameters and the API key,
    utilizes the `_get_common_driver_args` helper from `BasePrompt`, adds
    OpenAi specific configurations, then instantiates a
    `OpenAiPromptDriver` and assigns it to the 'prompt_model_config'
    output parameter.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the OpenAiPrompt node.

        Calls the superclass initializer, then modifies the inherited 'model'
        parameter to use OpenAi specific models and sets a default.
        It also removes the 'seed' parameter inherited from `BasePrompt` as it's
        not directly supported by the OpenAi driver implementation.
        """
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for OpenAi specifics.
        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)

        # Remove the 'seed' parameter as it's not directly used by OpenAiPromptDriver.
        self.remove_parameter_by_name("seed")

        # Remove `top_k` parameter as it's not used by OpenAi.
        self.remove_parameter_by_name("top_k")

        # Replace `min_p` with `top_p` for OpenAi.
        self._replace_param_by_name(param_name="min_p", new_param_name="top_p", default_value=0.9)

    def process(self) -> None:
        """Processes the node configuration to create a OpenAiPromptDriver.

        Retrieves parameter values set on the node and the required API key from
        the node's configuration system. It constructs the arguments dictionary
        for the `OpenAiPromptDriver`, handles optional parameters and
        any necessary conversions (like 'min_p' to 'top_p'), instantiates the
        driver, and assigns it to the 'prompt_model_config' output parameter.

        Raises:
            KeyError: If the OpenAi API key is not found in the node configuration
                      (though `validate_before_workflow_run` should prevent this during execution).
        """
        # Retrieve all parameter values set on the node UI or via input connections.
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BasePrompt to get args like temperature, stream, max_attempts, etc.
        common_args = self._get_common_driver_args(params)

        # --- Prepare OpenAi Specific Arguments ---
        specific_args = {}

        # Retrieve the mandatory API key.
        specific_args["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)

        # Get the selected model.
        specific_args["model"] = self.get_parameter_value("model")

        # Handle parameters that go into 'extra_params' for OpenAi.
        extra_params = {}

        extra_params["top_p"] = self.get_parameter_value("top_p")

        # Assign extra_params if not empty
        if extra_params:
            specific_args["extra_params"] = extra_params

        # --- Combine Arguments and Instantiate Driver ---
        # Combine common arguments with OpenAi specific arguments.
        # Specific args take precedence if there's an overlap (though unlikely here).
        all_kwargs = {**common_args, **specific_args}

        # Create the OpenAi prompt driver instance.
        driver = GtOpenAiChatPromptDriver(**all_kwargs)

        # Set the output parameter 'prompt_model_config'.
        self.parameter_output_values["prompt_model_config"] = driver

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validates that the OpenAi API key is configured correctly.

        Calls the base class helper `_validate_api_key` with OpenAi-specific
        configuration details.
        """
        return self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=API_KEY_ENV_VAR,
            api_key_url=API_KEY_URL,
        )
