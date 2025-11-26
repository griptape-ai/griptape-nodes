from griptape.artifacts import ImageUrlArtifact
from griptape.drivers.prompt.base_prompt_driver import BasePromptDriver
from griptape.drivers.prompt.griptape_cloud_prompt_driver import GriptapeCloudPromptDriver
from griptape.structures import Structure
from griptape.tasks import PromptTask

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.agents.griptape_nodes_agent import GriptapeNodesAgent as GtAgent
from griptape_nodes_library.utils.error_utils import try_throw_error
from griptape_nodes_library.utils.image_utils import load_image_from_url_artifact

SERVICE = "Griptape"
API_KEY_URL = "https://cloud.griptape.ai/configuration/api-keys"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
MODEL_CHOICES = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-5",
    "o1",
    "o1-mini",
    "o3-mini",
    "gemini-3-pro",
]
DEFAULT_MODEL = MODEL_CHOICES[0]


class DescribeImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="agent",
                type="Agent",
                output_type="Agent",
                tooltip="An agent that can be used to describe the image.",
                default_value=None,
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str", "Prompt Model Config"],
                type="str",
                output_type="str",
                default_value=DEFAULT_MODEL,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                tooltip="Choose a model, or connect a Prompt Model Configuration or an Agent",
                traits={Options(choices=MODEL_CHOICES)},
                ui_options={"display_name": "prompt model"},
            )
        )
        self.add_parameter(
            Parameter(
                name="image",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                type="ImageArtifact",
                tooltip="The image you would like to describe",
                default_value=None,
                ui_options={"expander": True},
            )
        )
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                output_type="str",
                type="str",
                tooltip="Explain how you'd like to describe the image.",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "placeholder_text": "Explain the various aspects of the image you want to describe.",
                    "multiline": True,
                    "display_name": "description prompt",
                },
            ),
        )

        self.add_parameter(
            Parameter(
                name="description_only",
                input_types=["bool"],
                type="bool",
                tooltip="Only return the description of the image, no conversation",
                default_value=True,
            )
        )
        self.add_parameter(
            Parameter(
                name="output",
                output_type="str",
                type="str",
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={
                    "placeholder_text": "The description of the image",
                    "multiline": True,
                    "display_name": "output",
                },
            )
        )

    def validate_before_workflow_run(self) -> list[Exception] | None:
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/871
        exceptions = []
        api_key = GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR)
        # No need for the api key. These exceptions caught on other nodes.
        if self.parameter_values.get("agent", None) and self.parameter_values.get("driver", None):
            return None
        if not api_key:
            msg = f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        return exceptions if exceptions else None

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "agent":
            self.hide_parameter_by_name("model")

        if target_parameter.name == "model" and source_parameter.name == "prompt_model_config":
            # Check and see if the incoming connection is from a prompt model config or an agent.
            target_parameter.type = source_parameter.type
            # Remove ParameterMode.PROPERTY so it forces the node mark itself dirty & remove the value
            target_parameter.allowed_modes = {ParameterMode.INPUT}

            target_parameter.remove_trait(trait_type=target_parameter.find_elements_by_type(Options)[0])
            ui_options = target_parameter.ui_options
            ui_options["display_name"] = source_parameter.ui_options.get("display_name", source_parameter.name)
            target_parameter.ui_options = ui_options

        return super().after_incoming_connection(source_node, source_parameter, target_parameter)

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
    ) -> None:
        if target_parameter.name == "agent":
            self.show_parameter_by_name("model")
        # Check and see if the incoming connection is from an agent. If so, we'll hide the model parameter
        if target_parameter.name == "model":
            target_parameter.type = "str"
            # Enable PROPERTY so the user can set it
            target_parameter.allowed_modes = {ParameterMode.INPUT, ParameterMode.PROPERTY}

            target_parameter.add_trait(Options(choices=MODEL_CHOICES))
            target_parameter.set_default_value(DEFAULT_MODEL)
            target_parameter.default_value = DEFAULT_MODEL
            ui_options = target_parameter.ui_options
            ui_options["display_name"] = "prompt model"
            target_parameter.ui_options = ui_options
            self.set_parameter_value("model", DEFAULT_MODEL)

        return super().after_incoming_connection_removed(source_node, source_parameter, target_parameter)

    def process(self) -> AsyncResult[Structure]:
        # Get the parameters from the node
        params = self.parameter_values
        model_input = self.get_parameter_value("model")
        agent = None

        default_prompt_driver = GriptapeCloudPromptDriver(
            model=DEFAULT_MODEL,
            api_key=GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR),
            stream=False,  # TODO: enable once https://github.com/griptape-ai/griptape-cloud/issues/1593 is resolved
        )

        # If an agent is provided, we'll use and ensure it's using a PromptTask
        # If a prompt_driver is provided, we'll use that
        # If neither are provided, we'll create a new one with the selected model.
        # Otherwise, we'll just use the default model
        agent = self.get_parameter_value("agent")
        if isinstance(agent, dict):
            agent = GtAgent().from_dict(agent)
            # make sure the agent is using a PromptTask
            if not isinstance(agent.tasks[0], PromptTask):
                agent.add_task(PromptTask(prompt_driver=default_prompt_driver))
        elif isinstance(model_input, BasePromptDriver):
            agent = GtAgent(prompt_driver=model_input)
        elif isinstance(model_input, str):
            if model_input not in MODEL_CHOICES:
                model_input = DEFAULT_MODEL
            prompt_driver = GriptapeCloudPromptDriver(
                model=model_input,
                api_key=GriptapeNodes.SecretsManager().get_secret(API_KEY_ENV_VAR),
                stream=False,  # TODO: enable once https://github.com/griptape-ai/griptape-cloud/issues/1593 is resolved
            )
            agent = GtAgent(prompt_driver=prompt_driver)
        else:
            # If the agent is not provided, we'll create a new one with a default prompt driver
            agent = GtAgent(prompt_driver=default_prompt_driver)

        prompt = params.get("prompt", "")
        if prompt == "":
            prompt = "Describe the image"

        get_description_only = self.get_parameter_value("description_only")
        if get_description_only:
            prompt += "\n\nOutput image description only."

        image_artifact = params.get("image", None)

        if isinstance(image_artifact, ImageUrlArtifact):
            image_artifact = load_image_from_url_artifact(image_artifact)
        if image_artifact is None:
            self.parameter_output_values["output"] = "No image provided"
            return

        # Run the agent
        yield lambda: agent.run([prompt, image_artifact])
        self.parameter_output_values["output"] = agent.output.value
        # Insert a false memory to prevent the base64
        agent.insert_false_memory(prompt=prompt, output=self.parameter_output_values["output"])
        try_throw_error(agent.output)

        # Set the output value for the agent
        self.parameter_output_values["agent"] = agent.to_dict()
