import uuid

from griptape.artifacts import BaseArtifact, ImageUrlArtifact
from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.structures.agent import Agent
from griptape.tasks import PromptImageGenerationTask

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger
from griptape_nodes_library.utils.error_utils import try_throw_error

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
DEFAULT_MODEL = "dall-e-3"
DEFAULT_QUALITY = "hd"
DEFAULT_STYLE = "natural"


class GenerateImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # TODO(griptape): Give nodes a way to ask about the current state of their connections instead of forcing them to maintain
        # state: https://github.com/griptape-ai/griptape-nodes/issues/720
        self._has_connection_to_prompt = False

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
                name="image_model_config",
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
                ui_options={"multiline": True, "placeholder_text": "Enter your image generation prompt here."},
            )
        )
        self.add_parameter(
            Parameter(
                name="enhance_prompt",
                input_types=["bool"],
                type="bool",
                tooltip="None",
                default_value=False,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )
        self.add_parameter(
            Parameter(
                name="output",
                input_types=["ImageArtifact", "ImageUrlArtifact"],
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="logs",
                type="str",
                tooltip="None",
                default_value="Node hasn't begun yet",
                ui_options={"multiline": True},
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_node_before_run(self) -> list[Exception] | None:
        """Validates a node is configured correctly before a run is started. This prevents wasting time executing nodes if there is a known failure.

        Override this method in your Node classes to add custom validation logic to confirm that your Node
        will not encounter any issues before a run is started.

        If there are no errors, return None. Otherwise, collate all errors into a list of Exceptions. These
        Exceptions will be surfaced to the user in order to give them directed feedback for how to resolve
        the issues.

        Returns:
            list[Exception] | None: A list of Exceptions if validation fails, otherwise None.
        """
        # TODO(kate): Figure out how to wrap this so it's easily repeatable
        exceptions = []
        api_key = self.get_config_value(SERVICE, API_KEY_ENV_VAR)
        if not api_key:
            # If we have an agent or a driver, the lack of API key will be surfaced on them, not us.
            agent_val = self.parameter_values.get("agent", None)
            driver_val = self.parameter_values.get("driver", None)
            if agent_val is None and driver_val is None:
                msg = f"{API_KEY_ENV_VAR} is not defined"
                exceptions.append(KeyError(msg))

        # Validate that we have a prompt.
        prompt_value = self.parameter_values.get("prompt", None)
        # Ensure no empty prompt; if there's an input connection to this Parameter, that will be OK though.
        if (not prompt_value or prompt_value.isspace()) and (not self._has_connection_to_prompt):
            msg = "No prompt was provided. Cannot generate an image without a valid prompt."
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def process(self) -> AsyncResult:
        # Get the parameters from the node
        params = self.parameter_values
        agent = params.get("agent", None)
        if not agent:
            prompt_driver = GriptapeCloudPromptDriver(
                model="gpt-4o",
                api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR),
            )
            agent = Agent(prompt_driver=prompt_driver)
        else:
            agent = Agent.from_dict(agent)
        prompt = params.get("prompt", "")

        enhance_prompt = params.get("enhance_prompt", False)

        if enhance_prompt:
            logger.info("Enhancing prompt...")
            self.append_value_to_parameter("logs", "Enhancing prompt...\n")
            # agent.run is a blocking operation that will hold up the rest of the engine.
            # By using `yield lambda`, the engine can run this in the background and resume when it's done.
            result = yield lambda: agent.run(
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
            self.append_value_to_parameter("logs", "Finished enhancing prompt...\n")
            prompt = result.output
        else:
            logger.info("Prompt enhancement disabled.")
            self.append_value_to_parameter("logs", "Prompt enhancement disabled.\n")
        # Initialize driver kwargs with required parameters
        kwargs = {}

        # Driver
        driver_val = params.get("image_model_config", None)
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

        # Run the agent asynchronously
        self.append_value_to_parameter("logs", "Starting processing image..\n")
        yield lambda: self._create_image(agent, prompt)
        self.append_value_to_parameter("logs", "Finished processing image.\n")

        # Reset the agent
        agent._tasks = []

    def after_incoming_connection(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        # Record a connection to the prompt Parameter so that node validation doesn't get aggro
        if target_parameter.name == "prompt":
            self._has_connection_to_prompt = True

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        # Remove the state maintenance of the connection to the prompt Parameter
        if target_parameter.name == "prompt":
            self._has_connection_to_prompt = False

    def _create_image(self, agent: Agent, prompt: BaseArtifact | str) -> None:
        agent.run(prompt)
        static_url = GriptapeNodes.StaticFilesManager().save_static_file(agent.output.to_bytes(), f"{uuid.uuid4()}.png")
        url_artifact = ImageUrlArtifact(value=static_url)
        self.publish_update_to_parameter("output", url_artifact)
        try_throw_error(agent.output)
