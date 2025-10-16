"""Defines the GriptapeCloudPrompt node for configuring the Griptape Cloud Prompt Driver.

This module provides the `GriptapeCloudPrompt` class, which allows users
to configure and utilize the Griptape Cloud prompt service within the Griptape
Nodes framework. It inherits common prompt parameters from `BasePrompt`, sets
Griptape Cloud specific model options, requires a Griptape Cloud API key via
node configuration, and instantiates the `GriptapeCloudPromptDriver`.
"""

from typing import Any

import requests
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver as GtGriptapeCloudPromptDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.config.prompt.base_prompt import BasePrompt

# --- Constants ---

SERVICE = "Griptape"
BASE_URL = "https://cloud.griptape.ai"
API_KEY_URL = f"{BASE_URL}/configuration/api-keys"
CHAT_MODELS_URL = f"{BASE_URL}/api/models?model_type=chat"
MODEL_CHOICES_ARGS = [
    {
        "name": "claude-sonnet-4-20250514",
        "icon": "logos/anthropic.svg",
        "args": {"stream": True, "structured_output_strategy": "tool", "max_tokens": 64000},
    },
    {
        "name": "claude-3-7-sonnet",
        "icon": "logos/anthropic.svg",
        "args": {"stream": True, "structured_output_strategy": "tool", "max_tokens": 64000},
    },
    {
        "name": "deepseek.r1-v1",
        "icon": "logos/deepseek.svg",
        "args": {"stream": False, "structured_output_strategy": "tool", "top_p": None},
    },
    {
        "name": "gemini-2.5-flash-preview-05-20",
        "icon": "logos/google.svg",
        "args": {"stream": True, "structured_output_strategy": "tool"},
    },
    {
        "name": "gemini-2.0-flash",
        "icon": "logos/google.svg",
        "args": {"stream": True, "structured_output_strategy": "tool"},
    },
    {
        "name": "llama3-3-70b-instruct-v1",
        "icon": "logos/meta.svg",
        "args": {"stream": True, "structured_output_strategy": "tool"},
    },
    {
        "name": "llama3-1-70b-instruct-v1",
        "icon": "logos/meta.svg",
        "args": {"stream": True, "structured_output_strategy": "tool"},
    },
    {"name": "gpt-4.1", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "gpt-4.1-mini", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "gpt-4.1-nano", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "gpt-5", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "o1", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "o1-mini", "icon": "logos/openai.svg", "args": {"stream": True}},
    {"name": "o3-mini", "icon": "logos/openai.svg", "args": {"stream": True}},
]

MODEL_CHOICES = [model["name"] for model in MODEL_CHOICES_ARGS]
DEFAULT_MODEL = MODEL_CHOICES[8]

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"

# Current models available in the API as of 8/9/2025
# but not all of them work.
#     "gpt-4.1",
#     "claude-3-5-haiku",
#     "claude-3-7-sonnet",
#     "deepseek.r1-v1",
#     "gemini-2.0-flash",
#     "gpt-4.1-mini",
#     "gpt-4.1-nano",
#     "gpt-4o",
#     "gpt-4o-mini-transcribe",
#     "gpt-4o-transcribe",
#     "gpt-5",
#     "llama3-1-70b-instruct-v1",
#     "llama3-3-70b-instruct-v1",
#     "o1",
#     "o1-mini",
#     "o3",
#     "o3-mini",
#     "o4-mini",


class GriptapeCloudPrompt(BasePrompt):
    """Node for configuring and providing a Griptape Cloud Prompt Driver.

    Inherits from `BasePrompt` to leverage common LLM parameters. This node
    customizes the available models to those supported by Griptape Cloud,
    removes parameters not applicable to Griptape Cloud (like 'seed'), and
    requires a Griptape Cloud API key to be set in the node's configuration
    under the 'Griptape' service.

    The `process` method gathers the configured parameters and the API key,
    utilizes the `_get_common_driver_args` helper from `BasePrompt`, adds
    Griptape Cloud specific configurations, then instantiates a
    `GriptapeCloudPromptDriver` and assigns it to the 'prompt_model_config'
    output parameter.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the GriptapeCloudPrompt node.

        Calls the superclass initializer, then modifies the inherited 'model'
        parameter to use Griptape Cloud specific models and sets a default.
        It also removes the 'seed' parameter inherited from `BasePrompt` as it's
        not directly supported by the Griptape Cloud driver implementation.
        """
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for Griptape Cloud specifics.
        models, default_model = self._list_models()
        logger.debug(f"All models on Griptape Cloud: {models}")
        logger.debug(f"Default model on Griptape Cloud: {default_model}")

        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)
        model_param = self.get_parameter_by_name("model")
        if model_param is not None:
            model_param.ui_options = {"data": MODEL_CHOICES_ARGS}

        # Remove the 'seed' parameter as it's not directly used by GriptapeCloudPromptDriver.
        self.remove_parameter_element_by_name("seed")

        # Remove `top_k` parameter as it's not used by Griptape Cloud.
        self.remove_parameter_element_by_name("top_k")

        # Replace `min_p` with `top_p` for Griptape Cloud.
        self._replace_param_by_name(param_name="min_p", new_param_name="top_p", default_value=0.9)

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "model":
            if "deepseek" in value:
                self.hide_parameter_by_name("stream")
                self.hide_parameter_by_name("top_p")
            else:
                self.show_parameter_by_name("stream")
                self.show_parameter_by_name("top_p")

            # Check and see if max_tokens is defined in the model args
            model_args = next((model["args"] for model in MODEL_CHOICES_ARGS if model["name"] == value), {})
            if "max_tokens" in model_args:
                self.parameter_output_values["max_tokens"] = model_args["max_tokens"]
            else:
                self.parameter_output_values["max_tokens"] = -1

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Processes the node configuration to create a GriptapeCloudPromptDriver.

        Retrieves parameter values set on the node and the required API key from
        the node's configuration system. It constructs the arguments dictionary
        for the `GriptapeCloudPromptDriver`, handles optional parameters and
        any necessary conversions (like 'min_p' to 'top_p'), instantiates the
        driver, and assigns it to the 'prompt_model_config' output parameter.

        Raises:
            KeyError: If the Griptape Cloud API key is not found in the node configuration
                      (though `validate_before_workflow_run` should prevent this during execution).
        """
        # Retrieve all parameter values set on the node UI or via input connections.
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BasePrompt to get args like temperature, stream, max_attempts, etc.
        common_args = self._get_common_driver_args(params)

        # --- Prepare Griptape Cloud Specific Arguments ---
        specific_args = {}

        # Retrieve the mandatory API key.
        specific_args["api_key"] = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)

        # Get the selected model.
        model = self.get_parameter_value("model")
        specific_args["model"] = model

        # Handle parameters that go into 'extra_params' for Griptape Cloud.
        extra_params = {}
        if model not in ["o1", "o1-mini", "o3", "o3-mini"]:
            top_p = self.get_parameter_value("top_p")
            if top_p is not None:
                extra_params["top_p"] = top_p

        # Assign extra_params if not empty
        if extra_params:
            specific_args["extra_params"] = extra_params

        # --- Combine Arguments and Instantiate Driver ---
        # Combine common arguments with Griptape Cloud specific arguments.
        all_kwargs = {**common_args, **specific_args}

        # Override with model specific args
        selected_model = self.get_parameter_value("model")
        model_args = next((model["args"] for model in MODEL_CHOICES_ARGS if model["name"] == selected_model), {})

        # Update with model args and remove any that are None
        for arg, value in model_args.items():
            if value is None:
                all_kwargs.pop(arg, None)  # Remove if exists
                # Also remove from extra_params if it exists there
                if "extra_params" in all_kwargs and arg in all_kwargs["extra_params"]:
                    del all_kwargs["extra_params"][arg]
            else:
                all_kwargs[arg] = value

        # Clean up empty extra_params
        if "extra_params" in all_kwargs and not all_kwargs["extra_params"]:
            del all_kwargs["extra_params"]

        # Create the Griptape Cloud prompt driver instance.
        driver = GtGriptapeCloudPromptDriver(**all_kwargs)

        # Set the output parameter 'prompt_model_config'.
        self.parameter_output_values["prompt_model_config"] = driver

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validates that the Griptape Cloud API key is configured correctly.

        Calls the base class helper `_validate_api_key` with Griptape-specific
        configuration details.
        """
        return self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=API_KEY_ENV_VAR,
            api_key_url=API_KEY_URL,
        )

    def _list_models(self) -> tuple[list[str], str]:
        """Returns the list of available models from Griptape Cloud, and the default model.

        This method fetches the list of models from the Griptape Cloud API and
        returns them. If the API call fails, it falls back to the default list
        of models defined in the `MODEL_CHOICES` constant.

        Returns:
            tuple: A tuple containing a list of available model names and the default model name.
        """
        # Fetch the list of available models from the Griptape Cloud API.
        response = requests.get(
            CHAT_MODELS_URL,
            headers={"Authorization": f"Bearer {GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)}"},
            timeout=10,
        )
        response.raise_for_status()
        models_data = response.json()["models"]
        models = [model["model_name"] for model in models_data]
        default_model = next(filter(lambda x: x["default"], models_data))["model_name"]
        return models, default_model
