from griptape.artifacts import ImageUrlArtifact
from griptape.drivers.prompt.base_prompt_driver import BasePromptDriver
from griptape.drivers.prompt.griptape_cloud_prompt_driver import GriptapeCloudPromptDriver
from griptape.loaders import ImageLoader
from griptape.structures import Structure
from griptape.structures.agent import Agent
from griptape.tasks import PromptTask

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes_library.utils.error_utils import try_throw_error

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
DEFAULT_MODEL = "dall-e-3"
DEFAULT_QUALITY = "hd"
DEFAULT_STYLE = "natural"


class DescribeImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="agent_or_config",
                type="Agent",
                input_types=["Agent", "Prompt Model Config"],
                output_type="Agent",
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                type="ImageArtifact",
                tooltip="The image you would like to describe",
                default_value=None,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                output_type="str",
                type="str",
                tooltip="How would you like to describe the image",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"placeholder_text": "How would you like to describe the image", "multiline": True},
            ),
        )

        self.add_parameter(
            Parameter(
                name="output",
                output_type="str",
                type="str",
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"placeholder_text": "The description of the image", "multiline": True},
            )
        )

    def validate_before_workflow_run(self) -> list[Exception] | None:
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/871
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

    def process(self) -> AsyncResult[Structure]:
        # Get the parameters from the node
        params = self.parameter_values
        agent_or_config = params.get("agent_or_config", None)
        agent = None
        default_prompt_driver = GriptapeCloudPromptDriver(
            model="gpt-4o",
            api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR),
            stream=True,
        )

        # If no agent_or_config is provided, create a new agent with the default prompt driver
        # If an agent_or_config is provided, check if it's a valid agent or prompt_model_config
        # If it's a prompt_model_config, create a new agent with it
        # If it's an agent, make sure it has a PromptTask
        # If it's neither, raise an error
        if not agent_or_config:
            agent = Agent(prompt_driver=default_prompt_driver)
        elif isinstance(agent_or_config, BasePromptDriver):
            # Create a new agent with the prompt_model_config
            agent = Agent(prompt_driver=agent_or_config)
        elif isinstance(agent_or_config, dict):
            agent = Agent.from_dict(agent_or_config)
            # make sure the agent is using a PromptTask
            if not isinstance(agent.tasks[0], PromptTask):
                agent.add_task(PromptTask(prompt_driver=default_prompt_driver))
        else:
            msg = "agent_or_config must be an Agent or a prompt_model_config"
            raise TypeError(msg)

        prompt = params.get("prompt", "")
        if prompt == "":
            prompt = "Describe the image"
        image_artifact = params.get("image", None)

        if isinstance(image_artifact, ImageUrlArtifact):
            image_artifact = ImageLoader().parse(image_artifact.to_bytes())
        if image_artifact is None:
            self.parameter_output_values["output"] = "No image provided"
            return

        # Run the agent
        yield lambda: agent.run([prompt, image_artifact])
        self.parameter_output_values["output"] = agent.output.value
        try_throw_error(agent.output)
