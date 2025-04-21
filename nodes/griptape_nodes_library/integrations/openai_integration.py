from griptape.drivers.image_generation.openai import OpenAiImageGenerationDriver as GtOpenAiImageGenerationDriver
from griptape.drivers.prompt.openai import OpenAiChatPromptDriver as GtOpenAiChatPromptDriver

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options
from griptape_nodes.traits.slider import Slider

DEFAULT_PROMPT_MODEL = "gpt-4o"
PROMPT_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]

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


class OpenAi(DataNode):
    """Node for OpenAi Integration.

    This node creates OpenAiDrivers and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_parameter(
            Parameter(
                name="prompt_driver",
                output_type="PromptDriver",
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
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
        prompt_model_options = Options(choices=PROMPT_MODELS)
        image_model_options = Options(choices=IMAGE_GENERATION_MODELS)
        image_style_options = Options(choices=IMAGE_STYLE_OPTIONS)
        image_quality_options = Options(choices=IMAGE_QUALITY_OPTIONS)
        image_size_options = Options(choices=IMAGE_SIZE_OPTIONS)
        slider_options = Slider(min_val=1, max_val=100)

        with ParameterGroup(group_name="Prompt Generation", ui_options={"hide": True}) as prompt_driver_group:
            Parameter(
                name="prompt_model",
                type="str",
                default_value=DEFAULT_PROMPT_MODEL,
                tooltip="Choose a model",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={prompt_model_options},
            )
            Parameter(
                name="max_attempts_on_fail",
                type="int",
                default_value=2,
                tooltip="Maximum attempts on failure",
                traits={slider_options},
            )
            Parameter(
                name="min_p",
                input_types=["float"],
                type="float",
                output_type="float",
                default_value=0.1,
                tooltip="Minimum probability for sampling. Lower values will be more random.",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
            )
            Parameter(
                name="temperature",
                input_types=["float"],
                type="float",
                output_type="float",
                default_value=0.1,
                tooltip="Temperature for sampling",
                ui_options={"slider": {"min_val": 0.0, "max_val": 1.0}, "step": 0.01},
            )
            Parameter(
                name="seed",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=10342349342,
                tooltip="Seed for random number generation",
            )
            Parameter(
                name="use_native_tools",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                default_value=True,
                tooltip="Use native tools for the LLM.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
            Parameter(
                name="max_tokens",
                input_types=["int"],
                type="int",
                output_type="int",
                default_value=-1,
                tooltip="Maximum tokens to generate. If <=0, it will use the default based on the tokenizer.",
            )
            Parameter(
                name="stream",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                default_value=True,
                tooltip="Whether or not to stream the response.",
            )

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

        self.add_node_element(prompt_driver_group)
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

        # Prompt driver parameters
        prompt_kwargs = {}
        prompt_kwargs["model"] = params.get("prompt_model", DEFAULT_PROMPT_MODEL)
        response_format = params.get("response_format", None)
        seed = params.get("seed", None)
        stream = params.get("stream", False)
        temperature = params.get("temperature", None)
        use_native_tools = params.get("use_native_tools", False)
        max_tokens = params.get("max_tokens", -1)
        max_attempts = params.get("max_attempts_on_fail", None)
        top_p = None if params.get("min_p", None) is None else 1 - float(params["min_p"])

        if response_format == "json_object":
            response_format = {"type": "json_object"}
            prompt_kwargs["response_format"] = response_format
        if seed:
            prompt_kwargs["seed"] = seed
        if stream:
            prompt_kwargs["stream"] = stream
        if temperature:
            prompt_kwargs["temperature"] = temperature
        if max_attempts:
            prompt_kwargs["max_attempts"] = max_attempts
        if use_native_tools:
            prompt_kwargs["use_native_tools"] = use_native_tools
        if max_tokens > 0:
            prompt_kwargs["max_tokens"] = max_tokens

        prompt_kwargs["extra_params"] = {}
        if top_p:
            prompt_kwargs["extra_params"]["top_p"] = top_p

        # Create the prompt driver
        prompt_driver = GtOpenAiChatPromptDriver(api_key=api_key, **prompt_kwargs)

        image_generation_kwargs = {}

        image_generation_kwargs["model"] = params.get("image_model", DEFAULT_IMAGE_MODEL)
        image_generation_kwargs["quality"] = params.get("quality", IMAGE_QUALITY_DEFAULT)
        image_generation_kwargs["style"] = params.get("style", IMAGE_STYLE_DEFULT)
        image_generation_kwargs["quality"] = params.get("quality", IMAGE_QUALITY_DEFAULT)
        image_generation_kwargs["image_size"] = params.get("size", IMAGE_SIZE_DEFAULT)

        # Create the image generation driver
        image_generation_driver = GtOpenAiImageGenerationDriver(api_key=api_key, **image_generation_kwargs)

        # Set the output
        self.parameter_output_values["prompt_driver"] = prompt_driver
        self.parameter_output_values["image_generation_driver"] = image_generation_driver
