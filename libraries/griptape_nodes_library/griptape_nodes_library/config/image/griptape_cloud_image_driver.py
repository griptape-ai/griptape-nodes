from typing import Any

from griptape.drivers.image_generation.griptape_cloud import (
    GriptapeCloudImageGenerationDriver as GtGriptapeCloudImageGenerationDriver,
)

from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.button import Button
from griptape_nodes.traits.options import Options
from griptape_nodes_library.config.image.base_image_driver import BaseImageDriver

# --- Constants ---

SERVICE = "Griptape"
API_KEY_URL = "https://cloud.griptape.ai/configuration/api-keys"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
MODEL_CHOICES = ["gpt-image-1-mini", "gpt-image-1.5"]
DEFAULT_MODEL = MODEL_CHOICES[0]
AVAILABLE_SIZES = ["1024x1024", "1536x1024", "1024x1536"]
DEFAULT_SIZE = AVAILABLE_SIZES[0]

# Deprecated models and their replacements
DEPRECATED_MODELS = {
    "dall-e-3": "gpt-image-1-mini",
}


class GriptapeCloudImage(BaseImageDriver):
    """Node for Griptape Cloud Image Generation Driver.

    This node creates an Griptape Cloud image generation driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for Griptape Cloud specifics.
        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)

        # Update the 'size' parameter for Griptape Cloud specifics.
        self._update_option_choices(param="image_size", choices=AVAILABLE_SIZES, default=str(DEFAULT_SIZE))

        self.add_node_element(
            ParameterMessage(
                name="model_deprecation_notice",
                title="Model Deprecation Notice",
                variant="info",
                value="",
                traits={
                    Button(
                        full_width=True,
                        on_click=lambda _, __: self.hide_message_by_name("model_deprecation_notice"),
                    )
                },
                button_text="Dismiss",
                hide=True,
            )
        )

        # Add additional parameters specific to Griptape Cloud
        self.add_parameter(
            Parameter(
                name="quality",
                type="str",
                default_value="medium",
                tooltip="Select the quality for image generation.",
                traits={Options(choices=["low", "medium", "high"])},
            )
        )

    def before_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> Any:
        if parameter.name == "model" and isinstance(value, str) and value in DEPRECATED_MODELS:
            replacement = DEPRECATED_MODELS[value]
            message = self.get_message_by_name_or_element_id("model_deprecation_notice")
            if message is None:
                raise RuntimeError("model_deprecation_notice message element not found")  # noqa: TRY003, EM101
            message.value = f"The '{value}' model has been deprecated. The model has been updated to '{replacement}'. Please save your workflow to apply this change."
            self.show_message_by_name("model_deprecation_notice")
            value = replacement
        elif parameter.name == "model" and isinstance(value, str):
            self.hide_message_by_name("model_deprecation_notice")

        return super().before_value_set(parameter, value)

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BaseImageDriver to get common driver arguments
        common_args = self._get_common_driver_args(params)

        # --- Prepare Griptape Cloud Specific Arguments ---
        specific_args = {}

        # Retrieve the mandatory API key.
        specific_args["api_key"] = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)

        specific_args["quality"] = self.get_parameter_value("quality")

        all_kwargs = {**common_args, **specific_args}

        self.parameter_output_values["image_model_config"] = GtGriptapeCloudImageGenerationDriver(**all_kwargs)

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
