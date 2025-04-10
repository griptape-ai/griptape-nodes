from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.structures.agent import Agent
from griptape.tasks import PromptImageGenerationTask

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.utils.error_utils import try_throw_error

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
DEFAULT_MODEL = "dall-e-3"
DEFAULT_QUALITY = "hd"
DEFAULT_STYLE = "natural"


class CreateImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.category = "Agent"
        self.description = "Generate an image"

        self.add_parameter(
            Parameter(
                name="agent",
                type="Agent",
                input_types=["Agent", "dict"],
                output_type="Agent",
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="image_generation_driver",
                input_types=["Image Generation Driver"],
                output_type="Image Generation Driver",
                type="Image Generation Driver",
                tooltip="None",
                default_value="",
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                output_type="str",
                type="str",
                tooltip="None",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "Enter your image generation prompt here."},
            )
        )
        self.add_parameter(
            Parameter(name="enhance_prompt", input_types=["bool"], type="bool", tooltip="None", default_value=True)
        )
        self.add_parameter(
            Parameter(
                name="output",
                input_types=["ImageArtifact"],
                output_type="ImageArtifact",
                type="ImageArtifact",
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_node(self) -> list[Exception] | None:
        # TODO(kate): Figure out how to wrap this so it's easily repeatable
        exceptions = []
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        # No need for the api key. These exceptions caught on other nodes.
        if self.parameter_values.get("agent", None) and self.parameter_values.get("driver", None):
            return None
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        return exceptions if exceptions else None

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        agent = params.get("agent", None)
        if not agent:
            prompt_driver = GriptapeCloudPromptDriver(
                model="gpt-4o",
                api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR),
                stream=True,
            )
            agent = Agent(prompt_driver=prompt_driver)
        else:
            agent = Agent().from_dict(agent)
        prompt = params.get("prompt", "")
        enhance_prompt = params.get("enhance_prompt", True)

        if enhance_prompt:
            logger.info("Enhancing prompt...")
            result = agent.run(
                [
                    """
Enhance the following prompt for an image generation engine. Return only the image generation prompt.
Include unique details that make the subject stand out.
Specify a specific depth of field, and time of day.
Use dust in the air to create a sense of depth.
Use a slight vignetting on the edges of the image.
Use a color palette that is complementary to the subject.
Focus on qualities that will make this the most professional looking photo in the world.""",
                    prompt,
                ]
            )
            prompt = result.output
        else:
            logger.info("Prompt enhancement disabled.")
        # Initialize driver kwargs with required parameters
        kwargs = {}

        # Driver
        driver_val = params.get("driver", None)
        if driver_val:
            driver = driver_val
        else:
            driver = GriptapeCloudImageGenerationDriver(
                model=params.get("model", DEFAULT_MODEL),
                api_key=self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR),
            )
        kwargs["image_generation_driver"] = driver

        # Add the actual image gen *task
        agent.add_task(PromptImageGenerationTask(**kwargs))

        # Run the agent
        result = agent.run(prompt)
        self.parameter_output_values["output"] = result.output
        try_throw_error(agent.output)
        # Reset the agent
        agent._tasks = []
