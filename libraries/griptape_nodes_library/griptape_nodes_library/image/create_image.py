import uuid

from griptape.artifacts import BaseArtifact, ImageUrlArtifact
from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.structures.agent import Agent
from griptape.tasks import PromptImageGenerationTask

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
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

        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/720
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
                ui_options={"pulse_on_run": True},
            )
        )
        # Group for logging information.
        with ParameterGroup(group_name="Logs") as logs_group:
            Parameter(name="include_details", type="bool", default_value=False, tooltip="Include extra details.")

            Parameter(
                name="logs",
                type="str",
                tooltip="Displays processing logs and detailed events if enabled.",
                ui_options={"multiline": True, "placeholder_text": "Logs"},
                allowed_modes={ParameterMode.OUTPUT},
            )
        logs_group.ui_options = {"hide": True}  # Hide the logs group by default.

        self.add_node_element(logs_group)

    def validate_before_workflow_run(self) -> list[Exception] | None:
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/871
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
        prompt_error = self.validate_empty_parameter(param="prompt")
        if prompt_error and not self._has_connection_to_prompt:
            exceptions.append(prompt_error)

        return exceptions if exceptions else None

    def process(self) -> AsyncResult:
        # Get the parameters from the node
        params = self.parameter_values

        # Validate that we have a prompt.
        prompt = self.get_parameter_value("prompt")
        exception = self.validate_empty_parameter(param="prompt")
        if exception:
            raise exception

        agent = params.get("agent", None)
        if not agent:
            prompt_driver = GriptapeCloudPromptDriver(
                model="gpt-4o",
                api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR),
            )
            agent = Agent(prompt_driver=prompt_driver)
        else:
            agent = Agent.from_dict(agent)

        # Check if we have a connection to the prompt parameter
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
Focus on qualities that will make this the most professional looking photo in the world.
IMPORTANT: Output must be a single, raw prompt string for an image generation model. Do not include any preamble, explanation, or conversational language.""",
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
        modified_parameters_set: set[str],
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        # Record a connection to the prompt Parameter so that node validation doesn't get aggro
        if target_parameter.name == "prompt":
            self._has_connection_to_prompt = True
            modified_parameters_set.add("prompt")
            # hey.. what if we just remove the property mode from the prompt parameter?
            if ParameterMode.PROPERTY in target_parameter.allowed_modes:
                target_parameter.allowed_modes.remove(ParameterMode.PROPERTY)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        # Remove the state maintenance of the connection to the prompt Parameter
        if target_parameter.name == "prompt":
            self._has_connection_to_prompt = False
            modified_parameters_set.add("prompt")
            # If we have no connections to the prompt parameter, add the property mode back
            target_parameter.allowed_modes.add(ParameterMode.PROPERTY)

    def _create_image(self, agent: Agent, prompt: BaseArtifact | str) -> None:
        agent.run(prompt)
        static_url = GriptapeNodes.StaticFilesManager().save_static_file(agent.output.to_bytes(), f"{uuid.uuid4()}.png")
        url_artifact = ImageUrlArtifact(value=static_url)
        self.publish_update_to_parameter("output", url_artifact)
        try_throw_error(agent.output)
