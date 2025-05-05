from typing import Any

from griptape.drivers.image_generation.openai import (
    OpenAiImageGenerationDriver as GtOpenAiImageGenerationDriver,
)

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes_library.config.image.base_image_driver import BaseImageDriver

# --- Constants ---

SERVICE = "OpenAI"
API_KEY_URL = "https://platform.openai.com/api-keys"
API_KEY_ENV_VAR = "OPENAI_API_KEY"
MODEL_CHOICES = ["dall-e-3", "dall-e-2"]
DALL_E_2_SIZES = ["256x256", "512x512", "1024x1024"]
DALL_E_3_SIZES = ["1024x1024", "1024x1792", "1792x1024"]
DEFAULT_MODEL = MODEL_CHOICES[0]
DEFAULT_SIZE = DALL_E_3_SIZES[0]


class OpenAiImage(BaseImageDriver):
    """Node for OpenAI Image Generation Driver.

    This node creates an OpenAI image generation driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # --- Customize Inherited Parameters ---

        # Update the 'model' parameter for Griptape Cloud specifics.
        self._update_option_choices(param="model", choices=MODEL_CHOICES, default=DEFAULT_MODEL)

        # Update the 'size' parameter for Griptape Cloud specifics.
        self._update_option_choices(param="image_size", choices=DALL_E_3_SIZES, default=DEFAULT_SIZE)

        # Add additional parameters specific to Griptape Cloud
        self.add_parameter(
            Parameter(
                name="style",
                type="str",
                default_value="vivid",
                tooltip="Select the style for image generation.",
                traits={Options(choices=["vivid", "natural"])},
            )
        )

        self.add_parameter(
            Parameter(
                name="quality",
                type="str",
                default_value="hd",
                tooltip="Select the quality for image generation.",
                traits={Options(choices=["hd", "standard"])},
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any, modified_parameters_set: set[str]) -> None:
        """Certain options are only available for certain models."""
        if parameter.name == "model":
            # If the model is DALL-E 2, update the size options accordingly
            toggle_params = ["style", "quality"]
            if value == "dall-e-2":
                self._update_option_choices(param="image_size", choices=DALL_E_2_SIZES, default=DALL_E_2_SIZES[2])
                # hide style and quality parameters
                for param in toggle_params:
                    toggle_param = self.get_parameter_by_name(param)
                    if toggle_param is not None:
                        toggle_param._ui_options["hide"] = True
            else:
                self._update_option_choices(param="image_size", choices=DALL_E_3_SIZES, default=DALL_E_3_SIZES[0])
                # hide style and quality parameters
                for param in toggle_params:
                    toggle_param = self.get_parameter_by_name(param)
                    if toggle_param is not None:
                        toggle_param._ui_options["hide"] = False

        return super().after_value_set(parameter, value, modified_parameters_set)

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BaseImageDriver to get common driver arguments
        common_args = self._get_common_driver_args(params)

        # --- Prepare Griptape Cloud Specific Arguments ---
        specific_args = {}

        # Retrieve the mandatory API key.
        specific_args["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)

        if self.get_parameter_value("model") == "dall-e-3":
            specific_args["style"] = self.get_parameter_value("style")
            specific_args["quality"] = self.get_parameter_value("quality")

        all_kwargs = {**common_args, **specific_args}

        self.parameter_output_values["image_model_config"] = GtOpenAiImageGenerationDriver(**all_kwargs)

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
