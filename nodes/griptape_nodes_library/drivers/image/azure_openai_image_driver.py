from griptape.drivers.image_generation.azure_openai_image_generation_driver import AzureOpenAiImageGenerationDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.drivers.image.base_image_driver import DRIVER_DICT, BaseImageDriver

# AZURE DICT OVERRIDES
AZURE_DICT = DRIVER_DICT.copy()
AZURE_DICT["config"] = {
    "service_key_field": [
        ("Microsoft Azure", "AZURE_OPENAI_DALL_E_3_API_KEY", "api_key"),
        ("Microsoft Azure", "AZURE_OPENAI_DALL_E_3_DEPLOYMENT_ID", "azure_deployment"),
        ("Microsoft Azure", "AZURE_OPENAI_DALL_E_3_ENDPOINT", "azure_endpoint"),
    ],
    "driver": AzureOpenAiImageGenerationDriver,
}

# AZURE DICT APPENDS - this is why we imported DRIVER_DICT, to allow appends instead of only overrides
AZURE_DICT["models"]["dall-e-3"]["params"]["azure_deployment"] = {"default": "dall-e-3"}
AZURE_DICT["models"]["dall-e-2"]["params"]["azure_deployment"] = {"default": "dall-e-2"}


class AzureOpenAiImage(BaseImageDriver):
    """Node for Azure OpenAI Image Generation Driver."""

    def __init__(self, **kwargs) -> None:
        super().__init__(driver_dict=AZURE_DICT, **kwargs)
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
