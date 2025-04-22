from griptape.drivers.image_generation.azure_openai_image_generation_driver import (
    AzureOpenAiImageGenerationDriver as GtAzureOpenAiImageGenerationDriver,
)

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.drivers.image.base_image_driver import BaseImageDriver

# Define the driver dictionary with Azure-specific configuration
DRIVER_DICT = {
    "config": {
        "service": "Microsoft Azure",
        "api_key": "AZURE_OPENAI_DALL_E_3_API_KEY",
        "azure_endpoint": "AZURE_OPENAI_DALL_E_3_ENDPOINT",
        "driver": GtAzureOpenAiImageGenerationDriver,
    }
}


class AzureOpenAiImage(BaseImageDriver):
    """Node for Azure OpenAI Image Generation Driver."""

    def __init__(self, **kwargs) -> None:
        super().__init__(driver_dict=DRIVER_DICT, **kwargs)
        self.add_parameter(
            Parameter(
                name="azure_deployment",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=self.model_default,  # Use the default model as deployment name
                tooltip="Enter the deployment name for the image generation model.",
            )
        )
