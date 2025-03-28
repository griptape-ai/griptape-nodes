from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.drivers.base_driver import BaseDriverNode
from griptape_nodes_library.utils.env_utils import getenv

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
DEFAULT_MODEL = "dall-e-3"
DEFAULT_QUALITY = "hd"
DEFAULT_STYLE = "natural"


class BaseImageDriverNode(BaseDriverNode):
    """Node for OpenAi Image Generation Driver.

    This node creates an OpenAi image generation driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="quality",
                allowed_types=["str"],
                default_value="",
                tooltip="",
            )
        )
        self.add_parameter(
            Parameter(
                name="style",
                allowed_types=["str"],
                default_value="",
                tooltip="",
            )
        )

        driver_parameter = self.get_parameter_by_name("driver")
        if driver_parameter is not None:
            driver_parameter.allowed_types = ["BaseImageGenerationDriver"]

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # Initialize kwargs with required parameters
        kwargs = {}
        kwargs["api_key"] = self.getenv(service=SERVICE, value=API_KEY_ENV_VAR)

        kwargs["model"] = params.get("model", DEFAULT_MODEL)
        kwargs["quality"] = params.get("quality", DEFAULT_QUALITY)
        kwargs["style"] = params.get("style", DEFAULT_STYLE)

        # Create the driver
        driver = GriptapeCloudImageGenerationDriver(**kwargs)

        # Set the output
        self.parameter_output_values["driver"] = driver

    def validate_node(self) -> list[Exception] | None:
        # Items here are openai api key
        exceptions = []
        api_key = getenv(SERVICE, API_KEY_ENV_VAR)
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        return exceptions if exceptions else None
