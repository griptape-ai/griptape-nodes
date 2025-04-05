from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver

from griptape_nodes.exe_types.core_types import Parameter
from nodes.griptape_nodes_library.drivers.image.base_image_driver import BaseImageDriverNode

SERVICE = "Griptape"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
DEFAULT_MODEL = "dall-e-3"
DEFAULT_SIZE = "1024x1024"
AVAILABLE_MODELS = ["dall-e-3"]
AVAILABLE_SIZES = ["1024x1024", "1024x1792", "1792x1024"]


class GriptapeCloudImageDriverNode(BaseImageDriverNode):
    """Node for Griptape Cloud Image Generation Driver.

    This node creates an Griptape Cloud image generation driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Add additional parameters specific to Azure OpenAI
        self.add_parameter(
            Parameter(
                name="image_generation_model",
                type="str",
                default_value=DEFAULT_MODEL,
                tooltip="Select the model for image generation.",
            )
        )
        self.add_parameter(
            Parameter(
                name="image_deployment_name",
                type="str",
                default_value=DEFAULT_MODEL,
                tooltip="Enter the deployment name for the image generation model.",
            )
        )
        self.add_parameter(
            Parameter(
                name="size",
                type="str",
                default_value=DEFAULT_SIZE,
                tooltip="Select the size of the generated image.",
            )
        )

        kwargs["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)

    def adjust_size_based_on_model(self, model, size) -> str:
        """Adjust the image size based on the selected model's capabilities.

        Args:
            model (str): The image generation model
            size (str): The requested image size

        Returns:
            str: The adjusted image size
        """
        # Pick the appropriate size based on the model
        if model == "dall-e-3" and size in ["256x256", "512x512"]:
            size = "1024x1024"
        return size

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # Get model and deployment information
        model = params.get("image_generation_model", DEFAULT_MODEL)

        # Get and adjust size
        size = params.get("size", DEFAULT_SIZE)
        size = self.adjust_size_based_on_model(model, size)

        # Initialize kwargs with required parameters
        kwargs = {
            "model": model,
            "api_key": self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR),
            "image_size": size,
        }

        self.parameter_output_values["driver"] = GriptapeCloudImageGenerationDriver(**kwargs)

    def validate_node(self) -> list[Exception] | None:
        exceptions = []
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions

        return None
