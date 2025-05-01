"""Defines the OpenAiPrompt node for configuring the OpenAi Prompt Driver.

This module provides the `OpenAiPrompt` class, which allows users
to configure and utilize the OpenAi prompt service within the Griptape
Nodes framework. It inherits common prompt parameters from `BasePrompt`, sets
OpenAi specific model options, requires a OpenAi API key via
node configuration, and instantiates the `OpenAiPromptDriver`.
"""

from griptape.drivers.prompt.amazon_bedrock import AmazonBedrockPromptDriver as GtAmazonBedrockPromptDriver

from griptape_nodes_library.config.prompt.base_prompt import BasePrompt

# --- Constants ---

SERVICE = "Amazon"
API_KEY_URL = "https://console.aws.amazon.com/iam/home?#/security_credentials"
AWS_ACCESS_KEY_ID_ENV_VAR = "AWS_ACCESS_KEY_ID"
AWS_DEFAULT_REGION_ENV_VAR = "AWS_DEFAULT_REGION"
AWS_SECRET_ACCCESS_KEY_ENV_VAR = "AWS_SECRET_ACCESS_KEY"  # noqa: S105
MODEL_CHOICES = [
    "anthropic.claude-3-5-sonnet-20240620-v1:0",
    "anthropic.claude-3-opus-20240229-v1:0",
    "anthropic.claude-3-sonnet-20240229-v1:0",
    "anthropic.claude-3-haiku-20240307-v1:0",
    "amazon.titan-text-premier-v1:0",
    "amazon.titan-text-express-v1",
    "amazon.titan-text-lite-v1",
]
DEFAULT_MODEL = MODEL_CHOICES[0]


class AmazonBedrockPrompt(BasePrompt):
    """Node for configuring and providing a Amazon Bedrock Chat Prompt Driver.

    Inherits from `BasePrompt` to leverage common LLM parameters. This node
    customizes the available models to those supported by Amazon Bedrock,
    removes parameters not applicable to Amazon Bedrock (like 'seed'), and
    requires a Amazon Bedrock API key to be set in the node's configuration
    under the 'Amazon Bedrock' service.

    The `process` method gathers the configured parameters and the API key,
    utilizes the `_get_common_driver_args` helper from `BasePrompt`, adds
    Amazon Bedrock specific configurations, then instantiates a
    `AmazonBedrockPromptDriver` and assigns it to the 'prompt_model_config'
    output parameter.
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the AmazonBedrockPrompt node.

        Calls the superclass initializer, then modifies the inherited 'model'
        parameter to use Amazon Bedrock specific models and sets a default.
        It also removes the 'seed' parameter inherited from `BasePrompt` as it's
        not directly supported by the Amazon Bedrock driver implementation.
        """
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for Amazon Bedrock specifics.
        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)

        # Remove the 'seed' parameter as it's not applicable for Amazon Bedrock.
        self.remove_parameter_by_name("seed")

        self.remove_parameter_by_name("min_p")
        self.remove_parameter_by_name("top_k")

        # Amazon Bedrock tends to fail if max_tokens isn't set
        self.set_parameter_value("max_tokens", 100)

    def process(self) -> None:
        """Processes the node configuration to create a AmazonBedrockPromptDriver.

        Retrieves parameter values set on the node and the required API key from
        the node's configuration system. It constructs the arguments dictionary
        for the `AmazonBedrockPromptDriver`, instantiates the
        driver, and assigns it to the 'prompt_model_config' output parameter.

        Raises:
            KeyError: If the Amazon Bedrock API key is not found in the node configuration
                      (though `validate_node` should prevent this during execution).
        """
        # Retrieve all parameter values set on the node UI or via input connections.
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BasePrompt to get args like temperature, stream, max_attempts, etc.
        common_args = self._get_common_driver_args(params)

        # --- Prepare OpenAi Specific Arguments ---
        specific_args = {}

        # Get the selected model.
        specific_args["model"] = self.get_parameter_value("model")
        # Handle parameters that go into 'extra_params' for Amazon Bedrock.

        extra_params = {}

        # Assign extra_params if not empty
        if extra_params:
            specific_args["extra_params"] = extra_params

        # --- Combine Arguments and Instantiate Driver ---
        # Combine common arguments with Amazon Bedrock specific arguments.
        # Specific args take precedence if there's an overlap (though unlikely here).
        all_kwargs = {**common_args, **specific_args}

        # Create the Amazon Bedrock prompt driver instance.
        driver = GtAmazonBedrockPromptDriver(**all_kwargs)

        # Set the output parameter 'prompt_model_config'.
        self.parameter_output_values["prompt_model_config"] = driver

    def validate_node(self) -> list[Exception] | None:
        """Validates that the Amazon Bedrock API key is configured correctly.

        Calls the base class helper `_validate_api_key` with Amazon Bedrock-specific
        configuration details.
        """
        return self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=AWS_ACCESS_KEY_ID_ENV_VAR,
            api_key_url=API_KEY_URL,
        )
