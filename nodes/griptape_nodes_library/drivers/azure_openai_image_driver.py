from griptape.drivers.image_generation.azure_openai_image_generation_driver import AzureOpenAiImageGenerationDriver

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes_library.drivers.base_image_driver import BaseImageDriverNode

AZURE_ENDPOINT_ENV_VAR = "AZURE_OPENAI_DALL_E_3_ENDPOINT"
API_KEY_ENV_VAR = "AZURE_OPENAI_DALL_E_3_API_KEY"
SERVICE = "Microsoft Azure"
DEFAULT_MODEL = "dall-e-3"
DEFAULT_SIZE = "1024x1024"
AVAILABLE_MODELS = ["dall-e-3", "dall-e-2"]
AVAILABLE_SIZES = ["256x256", "512x512", "1024x1024", "1024x1792", "1792x1024"]


class AzureOpenAiChatPromptDriverNode(BaseImageDriverNode):
    """Node for Azure OpenAI Image Generation Driver.

    This node creates an Azure OpenAI image generation driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Add additional parameters specific to Azure OpenAI
        self.add_parameter(
            Parameter(
                name="image_generation_model",
                input_types=["str"],
                default_value=DEFAULT_MODEL,
                tooltip="Select the model for image generation.",
            )
        )
        self.add_parameter(
            Parameter(
                name="image_deployment_name",
                input_types=["str"],
                default_value=DEFAULT_MODEL,
                tooltip="Enter the deployment name for the image generation model.",
            )
        )
        self.add_parameter(
            Parameter(
                name="size",
                input_types=["str"],
                default_value=DEFAULT_SIZE,
                tooltip="Select the size of the generated image.",
            )
        )
        self.add_parameter(
            Parameter(
                name="image_endpoint_env_var",
                input_types=["str"],
                default_value=AZURE_ENDPOINT_ENV_VAR,
                tooltip="Enter the name of the environment variable for AZURE_OPENAI_DALL_E_3_ENDPOINT, not the actual endpoint.",
            )
        )
        self.add_parameter(
            Parameter(
                name="image_api_key_env_var",
                input_types=["str"],
                default_value=API_KEY_ENV_VAR,
                tooltip="Enter the name of the environment variable for AZURE_OPENAI_DALL_E_3_API_KEY, not the actual API key.",
            )
        )
        self.add_parameter(
            Parameter(
                name="api_key",
                input_types=["str"],
                default_value="",
                tooltip="The Azure OpenAI API key",
            )
        )
        self.add_parameter(
            Parameter(
                name="api_base",
                input_types=["str"],
                default_value="",
                tooltip="The Azure OpenAI API base URL",
            )
        )
        self.add_parameter(
            Parameter(
                name="api_version",
                input_types=["str"],
                default_value="",
                tooltip="The Azure OpenAI API version",
            )
        )
        self.add_parameter(
            Parameter(
                name="deployment_name",
                input_types=["str"],
                default_value="",
                tooltip="The Azure OpenAI deployment name",
            )
        )
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                default_value="",
                tooltip="The model to use for image generation",
            )
        )

    def adjust_size_based_on_model(self, model, size) -> str:
        """Adjust the image size based on the selected model's capabilities.

        Args:
            model (str): The image generation model
            size (str): The requested image size

        Returns:
            str: The adjusted image size
        """
        # Pick the appropriate size based on the model
        if model == "dall-e-2" and size in ["1024x1792", "1792x1024"]:
            size = "1024x1024"
        if model == "dall-e-3" and size in ["256x256", "512x512"]:
            size = "1024x1024"
        return size

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # Get model and deployment information
        model = params.get("image_generation_model", DEFAULT_MODEL)
        deployment_name = params.get("image_deployment_name", model)  # Default to model name if not specified

        # Get and adjust size
        size = params.get("size", DEFAULT_SIZE)
        size = self.adjust_size_based_on_model(model, size)

        # Initialize kwargs with required parameters
        kwargs = {
            "model": model,
            "api_key": self.getenv(service=SERVICE, value=API_KEY_ENV_VAR),
            "azure_endpoint": self.getenv(service=SERVICE, value=AZURE_ENDPOINT_ENV_VAR),
            "azure_deployment": deployment_name,
            "image_size": size,
        }

        self.parameter_output_values["driver"] = AzureOpenAiImageGenerationDriver(**kwargs)


if __name__ == "__main__":
    from griptape.structures.agent import Agent
    from griptape.tasks import PromptImageGenerationTask

    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    def getenv(service: str, value: str) -> str:
        config = GriptapeNodes.ConfigManager()
        api_key = config.get_config_value(f"env.{service}.{value}")
        return api_key

    kwargs: dict = {
        "model": DEFAULT_MODEL,
        "api_key": getenv(service=SERVICE, value=API_KEY_ENV_VAR),
        "azure_endpoint": getenv(service=SERVICE, value=AZURE_ENDPOINT_ENV_VAR),
        "azure_deployment": DEFAULT_MODEL,
        "image_size": DEFAULT_SIZE,
    }

    driver = AzureOpenAiImageGenerationDriver(**kwargs)
    agent = Agent(stream=True)
    agent.add_task(PromptImageGenerationTask(image_generation_driver=driver))

    # Run the agent
    result = agent.run("soup")
