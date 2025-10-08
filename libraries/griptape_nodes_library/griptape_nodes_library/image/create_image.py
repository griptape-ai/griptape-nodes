from typing import Any

import requests
from griptape.artifacts import BaseArtifact, ImageUrlArtifact
from griptape.drivers.image_generation.base_image_generation_driver import BaseImageGenerationDriver
from griptape.drivers.image_generation.griptape_cloud import GriptapeCloudImageGenerationDriver
from griptape.drivers.prompt.griptape_cloud import GriptapeCloudPromptDriver
from griptape.tasks import PromptImageGenerationTask

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.agents.griptape_nodes_agent import GriptapeNodesAgent as GtAgent
from griptape_nodes_library.utils.error_utils import try_throw_error
from griptape_nodes_library.utils.file_utils import generate_filename

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
SERVICE = "Griptape"
MODEL_CHOICES = ["dall-e-3", "gpt-image-1"]
GPT_IMAGE_SIZES = ["1024x1024", "1536x1024", "1024x1536"]
DALL_E_3_SIZES = ["1024x1024", "1024x1792", "1792x1024"]
DEFAULT_MODEL = MODEL_CHOICES[0]
DEFAULT_SIZE = DALL_E_3_SIZES[0]


class GenerateImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/720
        self._has_connection_to_prompt = False

        self.add_parameter(
            Parameter(
                name="agent",
                type="Agent",
                input_types=["Agent"],
                output_type="Agent",
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str", "Image Generation Driver"],
                type="str",
                default_value=DEFAULT_MODEL,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                tooltip="Select the model you want to use from the available options.",
                traits={Options(choices=MODEL_CHOICES)},
                ui_options={"display_name": "image model"},
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
                name="image_size",
                type="str",
                default_value=DEFAULT_SIZE,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                tooltip="Select the size of the generated image.",
                traits={Options(choices=DALL_E_3_SIZES)},
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
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                ui_options={"pulse_on_run": True},
                settable=False,  # Ensures this serializes on save, but don't let user set it.
            )
        )
        # Group for logging information.
        with ParameterGroup(name="Logs") as logs_group:
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
        api_key = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)
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

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        """Certain options are only available for certain models."""
        if parameter.name == "output_format":
            if value == "jpeg":
                self.show_parameter_by_name("output_compression")
            else:
                self.hide_parameter_by_name("output_compression")

        if parameter.name == "model":
            # "model" supports either a string OR an Image Generation Driver. We can serialize strings, but not driver objects.
            if isinstance(value, str):
                # If the model is gpt-image-1, update the size options accordingly
                if value == "gpt-image-1":
                    self._update_option_choices(param="image_size", choices=GPT_IMAGE_SIZES, default=GPT_IMAGE_SIZES[0])
                elif value == "dall-e-3":
                    self._update_option_choices(param="image_size", choices=DALL_E_3_SIZES, default=DALL_E_3_SIZES[0])

                # Strings can serialize.
                parameter.serializable = True
            else:
                # It's an Image Generation Driver, which we canNOT serialize.
                parameter.serializable = False

        return super().after_value_set(parameter, value)

    def process(self) -> AsyncResult:
        # Get the parameters from the node
        params = self.parameter_values

        # Validate that we have a prompt.
        orig_prompt = self.get_parameter_value("prompt")

        exception = self.validate_empty_parameter(param="prompt")
        if exception:
            raise exception

        agent = self.get_parameter_value("agent")
        if not agent:
            prompt_driver = GriptapeCloudPromptDriver(
                model="gpt-4o",
                api_key=GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR),
                stream=True,
            )
            agent = GtAgent(prompt_driver=prompt_driver)
        else:
            agent = GtAgent.from_dict(agent)

        # Add some context to the prompt based on the agent's conversation memory.
        # We use this because otherwise the agent will not have the context of the prompt.
        # This is due to the fact that when you temporarily swap the task from a prompt_task to an image generation task,
        # the context is lost.
        prompt = agent.build_context(prompt=orig_prompt)

        # Check if we have a connection to the prompt parameter
        enhance_prompt = params.get("enhance_prompt", False)

        if enhance_prompt:
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
            self.append_value_to_parameter("logs", "Prompt enhancement disabled.\n")
        # Initialize driver kwargs with required parameters
        kwargs = {}

        # Driver
        model_input = self.get_parameter_value("model")
        driver = None
        if isinstance(model_input, BaseImageGenerationDriver):
            driver = model_input
        elif isinstance(model_input, str):
            if model_input not in MODEL_CHOICES:
                model_input = DEFAULT_MODEL
            driver = GriptapeCloudImageGenerationDriver(
                model=model_input,
                image_size=self.get_parameter_value("image_size"),
                api_key=GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR),
                # Don't retry on HTTP errors, we want to fail fast.
                ignored_exception_types=(requests.exceptions.HTTPError,),
            )
        else:
            driver = GriptapeCloudImageGenerationDriver(
                model=DEFAULT_MODEL,
                image_size=self.get_parameter_value("image_size"),
                api_key=GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR),
                ignored_exception_types=(requests.HTTPError,),
            )

        kwargs["image_generation_driver"] = driver

        # Set new Image Generation Task
        # Cool trick to swap the task of the agent from PromptTask to ImageGenerationTask
        agent.swap_task(PromptImageGenerationTask(**kwargs))

        # Run the agent asynchronously
        self.append_value_to_parameter("logs", "Starting processing image..\n")
        yield lambda: self._create_image(agent, prompt)
        self.append_value_to_parameter("logs", "Finished processing image.\n")

        # Create a false memory for the agent
        # This is because the agent will have the base64 image in its memory, which is huge.
        # So we replace it with a simple, false memory - but tell it is used a tool.
        agent.insert_false_memory(
            prompt=orig_prompt, output="I created an image based on your prompt.", tool="GenerateImageTool"
        )

        # Restore the task
        # Now restore the original prompt task for the agent.
        agent.restore_task()

        # Output the agent
        self.parameter_output_values["agent"] = agent.to_dict()

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        # Record a connection to the prompt Parameter so that node validation doesn't get aggro
        if target_parameter.name == "prompt":
            self._has_connection_to_prompt = True
            # hey.. what if we just remove the property mode from the prompt parameter?
            if ParameterMode.PROPERTY in target_parameter.allowed_modes:
                target_parameter.allowed_modes = target_parameter.allowed_modes - {ParameterMode.PROPERTY}

        if target_parameter.name == "model" and source_parameter.name == "image_model_config":
            # Check and see if the incoming connection is from a image model config.
            target_parameter.type = source_parameter.type
            target_parameter.remove_trait(trait_type=target_parameter.find_elements_by_type(Options)[0])
            ui_options = target_parameter.ui_options
            ui_options["display_name"] = source_parameter.name
            target_parameter.ui_options = ui_options
            target_parameter.allowed_modes = {ParameterMode.INPUT}

            self.hide_parameter_by_name("image_size")

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        # Remove the state maintenance of the connection to the prompt Parameter
        if target_parameter.name == "prompt":
            self._has_connection_to_prompt = False
            # If we have no connections to the prompt parameter, add the property mode back
            target_parameter.allowed_modes = target_parameter.allowed_modes | {ParameterMode.PROPERTY}

        # Check and see if the incoming connection is from an agent. If so, we'll hide the model parameter
        if target_parameter.name == "model":
            target_parameter.type = "str"
            # Enable PROPERTY so the user can set it
            target_parameter.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY}

            target_parameter.add_trait(Options(choices=MODEL_CHOICES))
            target_parameter.set_default_value(DEFAULT_MODEL)
            target_parameter.default_value = DEFAULT_MODEL
            ui_options = target_parameter.ui_options
            ui_options["display_name"] = "model"
            target_parameter.ui_options = ui_options
            self.set_parameter_value("model", DEFAULT_MODEL)
            self.show_parameter_by_name("image_size")

        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def _create_image(self, agent: GtAgent, prompt: BaseArtifact | str) -> None:
        agent.run(prompt)
        filename = generate_filename(
            node_name=self.name,
            suffix="_generated",
            extension="png",
        )
        static_url = GriptapeNodes.StaticFilesManager().save_static_file(agent.output.to_bytes(), filename)
        url_artifact = ImageUrlArtifact(value=static_url)
        self.publish_update_to_parameter("output", url_artifact)
        try_throw_error(agent.output)
