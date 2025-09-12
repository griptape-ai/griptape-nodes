from griptape.drivers.image_generation.griptape_cloud import (
    GriptapeCloudImageGenerationDriver as GtGriptapeCloudImageGenerationDriver,
)

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes_library.config.image.base_image_driver import BaseImageDriver

# --- Constants ---

SERVICE = "Griptape"
API_KEY_URL = "https://cloud.griptape.ai/configuration/api-keys"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
MODEL_CHOICES = ["dall-e-3"]
DEFAULT_MODEL = MODEL_CHOICES[0]
AVAILABLE_SIZES = ["1024x1024", "1024x1792", "1792x1024"]
DEFAULT_SIZE = AVAILABLE_SIZES[0]


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

        specific_args["style"] = self.get_parameter_value("style")
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
