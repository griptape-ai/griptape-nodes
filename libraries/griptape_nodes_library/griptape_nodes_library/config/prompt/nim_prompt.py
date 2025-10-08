"""Defines the NimPrompt node for configuring the OpenAi Prompt Driver.

This module provides the `NimPrompt` class, which allows users
to configure and utilize the OpenAi prompt service within the Griptape
Nodes framework. It inherits common prompt parameters from `BasePrompt`, sets
NVIDIA NIM specific model options, requires a NIM API key via
node configuration, and instantiates the `OpenAiChatPromptDriver`.
"""

from griptape.drivers.prompt.openai import OpenAiChatPromptDriver as GtOpenAiChatPromptDriver

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes_library.config.prompt.base_prompt import BasePrompt

# --- Constants ---

SERVICE = "Nvidia"
BASE_URL = "https://integrate.api.nvidia.com/v1"
API_KEY_URL = "https://build.nvidia.com/settings/api-keys"
API_KEY_ENV_VAR = "NVIDIA_API_KEY"
MODEL_CHOICES = [
    "deepseek-ai/deepseek-v3.1",
    "google/gemma-3-1b-it",
    "meta/llama-4-maverick-17b-128e-instruct",
    "meta/llama-4-scout-17b-16e-instruct",
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama3-8b-instruct",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
    "nvidia/nvidia-nemotron-nano-9b-v2",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "opengpt-x/teuken-7b-instruct-commercial-v0.4",
    "moonshotai/kimi-k2-instruct",
    "mistralai/magistral-small-2506",
]
DEFAULT_MODEL = MODEL_CHOICES[0]


class NimPrompt(BasePrompt):
    """Node for configuring and providing a NVIDIA Chat Prompt Driver.

    Inherits from `BasePrompt` to leverage common LLM parameters. This node
    customizes the available models to those supported by NVIDIA,
    removes parameters not applicable to NVIDIA (like 'seed'), and
    requires a NVIDIA API key to be set in the node's configuration
    under the 'NVIDIA' service.

    The `process` method gathers the configured parameters and the API key,
    utilizes the `_get_common_driver_args` helper from `BasePrompt`, adds
    NVIDIA specific configurations, then instantiates a
    `OpenAiChatPromptDriver` with NVIDIA specific configurations and assigns it to the 'prompt_model_config'
    output parameter.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the NimPrompt node.

        Calls the superclass initializer, then modifies the inherited 'model'
        parameter to use NVIDIA specific models and sets a default.
        It also removes the 'seed' parameter inherited from `BasePrompt` as it's
        not directly supported by the NVIDIA driver implementation.
        """
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for NVIDIA specifics.
        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)

        # Remove the 'seed' parameter
        self.remove_parameter_element_by_name("seed")

        # Remove `top_k` parameter as it's not used by NVIDIA.
        self.remove_parameter_element_by_name("top_k")

        # Replace `min_p` with `top_p` for NIM.
        self._replace_param_by_name(param_name="min_p", new_param_name="top_p", default_value=0.9)

    def process(self) -> None:
        """Processes the node configuration to create a NIM PromptDriver.

        Retrieves parameter values set on the node and the required API key from
        the node's configuration system. It constructs the arguments dictionary
        for the `OpenAiChatPromptDriver` with NVIDIA specific configurations, handles optional parameters and
        any necessary conversions (like 'min_p' to 'top_p'), instantiates the
        driver, and assigns it to the 'prompt_model_config' output parameter.

        Raises:
            KeyError: If the NVIDIA API key is not found in the node configuration
                      (though `validate_before_workflow_run` should prevent this during execution).
        """
        # Retrieve all parameter values set on the node UI or via input connections.
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BasePrompt to get args like temperature, stream, max_attempts, etc.
        common_args = self._get_common_driver_args(params)

        # --- Prepare NVIDIA Specific Arguments ---
        specific_args = {}

        # Retrieve the mandatory API key.
        specific_args["api_key"] = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)

        # Set the base URL for the NVIDIA API.
        specific_args["base_url"] = BASE_URL

        # Get the selected model.
        specific_args["model"] = self.get_parameter_value("model")

        # Handle parameters that go into 'extra_params' for NVIDIA.
        extra_params = {}

        extra_params["top_p"] = self.get_parameter_value("top_p")

        # Assign extra_params if not empty
        if extra_params:
            specific_args["extra_params"] = extra_params

        # --- Combine Arguments and Instantiate Driver ---
        # Combine common arguments with Nvidia specific arguments.
        # Specific args take precedence if there's an overlap (though unlikely here).
        all_kwargs = {**common_args, **specific_args}

        # Create the Nvidia prompt driver instance.
        driver = GtOpenAiChatPromptDriver(**all_kwargs)

        # Set the output parameter 'prompt_model_config'.
        self.parameter_output_values["prompt_model_config"] = driver

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validates that the Nvidia API key is configured correctly.

        Calls the base class helper `_validate_api_key` with Nvidia-specific
        configuration details.
        """
        return self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=API_KEY_ENV_VAR,
            api_key_url=API_KEY_URL,
        )
