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

SERVICE = "Griptape"
API_KEY_URL = "https://cloud.griptape.ai/configuration/api-keys"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
MODELS = ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4.5-preview", "o1", "o1-mini", "o3-mini"]
DEFAULT_MODEL = "gpt-4.1-mini"


class ExGriptapeCloudPrompt(BasePrompt):
    """Node for configuring and providing a Griptape Cloud Prompt Driver.

    Inherits from `BasePrompt` to leverage common LLM parameters. This node
    customizes the available models to those supported by Griptape Cloud,
    removes parameters not applicable to Griptape Cloud (like 'seed'), and
    requires a Griptape Cloud API key to be set in the node's configuration
    under the 'Griptape' service.

    The `process` method gathers the configured parameters and the API key,
    utilizes the `_get_common_driver_args` helper from `BasePrompt`, adds
    Griptape Cloud specific configurations, then instantiates a
    `GriptapeCloudPromptDriver` and assigns it to the 'prompt model config'
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

        # Remove `top_k` parameter as it's not used by Griptape Cloud.
        top_k_parameter = self.get_parameter_by_name("top_k")
        if top_k_parameter is not None:
            self.remove_parameter(top_k_parameter)

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

        # --- Get Common Driver Arguments ---
        # Use the helper method from BasePrompt to get args like temperature, stream, max_attempts, etc.
        common_args = self._get_common_driver_args(params)

        # --- Prepare Griptape Cloud Specific Arguments ---
        specific_args = {}

        # Retrieve the mandatory API key.
        specific_args["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)

        # Get the selected model.
        specific_args["model"] = self.get_parameter_value("model")

        # Handle parameters that go into 'extra_params' for Griptape Cloud.
        extra_params = {}

        # Convert 'min_p' (from BasePrompt) to 'top_p' if provided.
        min_p_value = self.get_parameter_value("min_p")  # Get min_p from node params
        if min_p_value is not None:
            # Griptape Cloud uses 'top_p' in extra_params.
            extra_params["top_p"] = 1.0 - float(min_p_value)
            # We got min_p via the common helper if it was set, but Griptape Cloud doesn't
            # directly use min_p, so remove it from common_args if it exists.
            common_args.pop("min_p", None)

        # Assign extra_params if not empty
        if extra_params:
            specific_args["extra_params"] = extra_params

        # --- Combine Arguments and Instantiate Driver ---
        # Combine common arguments with Griptape Cloud specific arguments.
        # Specific args take precedence if there's an overlap (though unlikely here).
        all_kwargs = {**common_args, **specific_args}

        # Create the Griptape Cloud prompt driver instance.
        driver = GtGriptapeCloudPromptDriver(**all_kwargs)

        # Set the output parameter 'prompt model config'.
        self.parameter_output_values["prompt model config"] = driver

    def validate_node(self) -> list[Exception] | None:
        """Validates that the Griptape Cloud API key is configured correctly.

        Calls the base class helper `_validate_api_key` with Griptape-specific
        configuration details.
        """
        return self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=API_KEY_ENV_VAR,
            api_key_url=API_KEY_URL,
        )
