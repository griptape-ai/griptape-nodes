"""Defines the BaseImageDriver node, an abstract base class for image generation driver configuration nodes.

This module provides the `BaseImageDriver` class, which serves as a foundation
for creating specific image generation driver configuration nodes within the Griptape
Nodes framework. It inherits from `BaseDriver` and defines common parameters
used by image generation drivers (like quality, style, etc.). The class configures
and instantiates a GriptapeCloudImageGenerationDriver with appropriate settings.
"""

from typing import Any

from griptape.drivers.image_generation.dummy import DummyImageGenerationDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.traits.options import Options
from griptape_nodes_library.config.base_driver import BaseDriver


class BaseImageDriver(BaseDriver):
    """Node for Griptape Cloud Image Generation Driver configuration.

    This node creates and configures a GriptapeCloudImageGenerationDriver instance
    with appropriate settings for image generation tasks. It provides parameters
    for customizing the image generation process, including quality and style settings.

    Key Features:
    - Configures image generation parameters (quality, style)
    - Manages API key validation and configuration
    - Creates and outputs a configured GriptapeCloudImageGenerationDriver
    - Supports customization of model, quality, and style parameters
    """

    def __init__(self, **kwargs) -> None:
        """Initializes the BaseImageDriver node.

        Sets up the node by calling the superclass initializer and adding
        parameters specific to image generation configuration. Also updates
        the inherited 'driver' output parameter to specify it's an Image
        Generation Driver.
        """
        super().__init__(**kwargs)

        # Update the inherited driver parameter to specify it's for image generation
        driver_parameter = self.get_parameter_by_name("driver")
        if driver_parameter is not None:
            driver_parameter.name = "image_model_config"
            driver_parameter.output_type = "Image Generation Driver"

        # --- Common Prompt Driver Parameters ---
        # These parameters represent settings frequently used by Image Generation drivers.
        # Subclasses will typically use these values when instantiating their specific driver.

        # Parameter for user messages.
        self.add_parameter(
            Parameter(
                name="message",
                type="str",
                default_value="⚠️ This node requires an API key to function.",
                tooltip="",
                allowed_modes={},  # type: ignore  # noqa: PGH003
                ui_options={"is_full_width": True, "multiline": True, "hide": True},
            )
        )
        # Parameter for model selection. Subclasses should populate the 'choices'.
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="",
                tooltip="Select the model you want to use from the available options.",
                traits={Options(choices=[])},
            )
        )
        self.add_parameter(
            Parameter(
                name="image_size",
                type="str",
                default_value="",
                tooltip="Select the size of the generated image.",
                traits={Options(choices=[])},
            )
        )

    def _get_common_driver_args(self, params: dict[str, Any]) -> dict[str, Any]:
        driver_args = {"model": params.get("model"), "image_size": params.get("image_size")}

        return driver_args

    def process(self) -> None:
        # Create a placeholder driver for the base class output type definition.
        # This ensures the output socket has the correct type ('Image Generation Driver')
        # even though this base node doesn't configure a real driver.
        driver = DummyImageGenerationDriver()

        # Set the output parameter with the placeholder driver.
        self.parameter_output_values["image_model_config"] = driver
