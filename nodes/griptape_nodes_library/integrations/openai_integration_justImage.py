from griptape.drivers.image_generation.openai import (  # noqa: INP001
    OpenAiImageGenerationDriver as GtOpenAiImageGenerationDriver,
)

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options

DEFAULT_IMAGE_MODEL = "dall-e-3"
IMAGE_GENERATION_MODELS = ["dall-e-3", "dall-e-2"]
IMAGE_STYLE_OPTIONS = ["vivid", "natural"]
IMAGE_STYLE_DEFULT = "natural"
IMAGE_QUALITY_DEFAULT = "standard"
IMAGE_QUALITY_OPTIONS = ["standard", "hd"]
IMAGE_SIZE_DEFAULT = "1024x1024"
IMAGE_SIZE_OPTIONS = ["256x256", "512x512", "1024x1024", "1024x1792", "1792x1024"]

API_KEY_ENV_VAR = "OPENAI_API_KEY"
SERVICE = "OpenAI"


class OpenAi_EG(DataNode):
    """Node for OpenAi Integration.

    This node creates OpenAiDrivers and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="image_generation_driver",
                output_type="Image Generation Driver",
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        # Options
        image_model_options = Options(choices=IMAGE_GENERATION_MODELS)
        image_style_options = Options(choices=IMAGE_STYLE_OPTIONS)
        image_quality_options = Options(choices=IMAGE_QUALITY_OPTIONS)
        image_size_options = Options(choices=IMAGE_SIZE_OPTIONS)

        with ParameterGroup(group_name="Image Generation", ui_options={"hide": True}) as image_generation_group:
            Parameter(
                name="image_model",
                type="str",
                default_value=DEFAULT_IMAGE_MODEL,
                tooltip="Choose a model",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={image_model_options},
            )
            Parameter(
                name="quality",
                type="str",
                default_value=IMAGE_QUALITY_DEFAULT,
                tooltip="",
                traits={image_quality_options},
            )
            Parameter(
                name="style",
                type="str",
                default_value=IMAGE_STYLE_DEFULT,
                tooltip="Image Style",
                traits={image_style_options},
            )
            Parameter(
                name="size",
                type="str",
                default_value=IMAGE_SIZE_DEFAULT,
                tooltip="Image Size",
                traits={image_size_options},
            )

        self.add_node_element(image_generation_group)

    def after_value_set(self, parameter: Parameter, value=None, modified_parameters_set=None) -> None:  # noqa: ARG002
        logger.info(f"after_value_set: {parameter.name} = {value}")
        if parameter.name == "image_model":
            # if image_model == "dall-e-3" then we have certain options for size.
            #
            quality_param = self.get_parameter_by_name("quality")
            style_param = self.get_parameter_by_name("style")
            if value == "dall-e-3":
                sizes = ["1024x1024", "1024x1792", "1792x1024"]

                # Hide the quality and style parameters
                if quality_param:
                    quality_param.ui_options = {"hide": True}
                if style_param:
                    style_param.ui_options = {"hide": True}
            else:
                sizes = ["256x256", "512x512", "1024x1024"]
                # Show the quality and style parameters
                if quality_param:
                    quality_param.ui_options = {"hide": False}
                if style_param:
                    style_param.ui_options = {"hide": False}
            # Get the image size parameter
            image_size_param = self.get_parameter_by_name("size")
            if image_size_param:
                children = image_size_param.children
                logger.info(f"children: {children[0]}")
                image_size_param.remove_trait(image_size_param.children[0])
                image_size_param.add_trait(Options(choices=sizes))
                image_size_param.ui_options = {"options": sizes}

            logger.info(f"image_size_param: {image_size_param}")
            logger.info(f"style_param: {style_param}")
            logger.info(f"quality_param: {quality_param}")

    def process(self) -> None:
        # Grab the API key

        # Get the parameters from the node
        params = self.parameter_values
        api_key = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)

        image_generation_kwargs = {}

        image_generation_kwargs["model"] = params.get("image_model", DEFAULT_IMAGE_MODEL)
        image_generation_kwargs["quality"] = params.get("quality", IMAGE_QUALITY_DEFAULT)
        image_generation_kwargs["style"] = params.get("style", IMAGE_STYLE_DEFULT)
        image_generation_kwargs["quality"] = params.get("quality", IMAGE_QUALITY_DEFAULT)
        image_generation_kwargs["image_size"] = params.get("size", IMAGE_SIZE_DEFAULT)

        # Create the image generation driver
        image_generation_driver = GtOpenAiImageGenerationDriver(api_key=api_key, **image_generation_kwargs)

        self.parameter_output_values["image_generation_driver"] = image_generation_driver
