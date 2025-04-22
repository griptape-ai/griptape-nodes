from griptape.drivers.image_generation.openai import OpenAiImageGenerationDriver

from griptape_nodes_library.drivers.image.base_image_driver import BaseImageDriver

DRIVER_DICT = {
    "config": {
        "service_key_field": [("OpenAI", "OPENAI_API_KEY", "api_key")],
        "driver": OpenAiImageGenerationDriver,
    }
    # Note: We're only overriding the config section, keeping models from parent class
}


class OpenAiImage(BaseImageDriver):
    """Node for OpenAI Image Generation Driver."""

    def __init__(self, **kwargs) -> None:
        super().__init__(driver_dict=DRIVER_DICT, **kwargs)
