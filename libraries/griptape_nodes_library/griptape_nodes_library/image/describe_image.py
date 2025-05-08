from griptape.artifacts import ImageUrlArtifact
from griptape.drivers.prompt.base_prompt_driver import BasePromptDriver
from griptape.drivers.prompt.griptape_cloud_prompt_driver import GriptapeCloudPromptDriver
from griptape.loaders import ImageLoader
from griptape.structures import Structure
from griptape.structures.agent import Agent
from griptape.tasks import PromptTask

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode, ControlNode
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.traits.options import Options
from griptape_nodes_library.utils.error_utils import try_throw_error

SERVICE = "Griptape"
API_KEY_URL = "https://cloud.griptape.ai/configuration/api-keys"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
MODEL_CHOICES = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4.5-preview",
    "o1",
    "o1-mini",
    "o3-mini",
]
DEFAULT_MODEL = MODEL_CHOICES[0]


def toggle_agent_model_visibility(target_param: str, show_fn: callable, hide_fn: callable, modified_set: set[str]):
    if target_param == "agent":
        hide_fn("model")
        modified_set.add("model")
    elif target_param == "model":
        hide_fn("agent")
        modified_set.add("agent")


class DescribeImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="agent",
                type="Agent",
                input_types=["Agent", "Prompt Model Config"],
                output_type="Agent",
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
                ui_options={"label": "[Optional] incoming Agent"},
            )
        )
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str", "Prompt Model Config"],
                type="str",
                output_type="str",
                default_value=DEFAULT_MODEL,
                tooltip="Select the model you want to use from the available options, or provide a custom model config",
                traits={Options(choices=MODEL_CHOICES)},
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

    def after_incoming_connection(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        toggle_agent_model_visibility(
            target_parameter.name,
            self.show_parameter_by_name,
            self.hide_parameter_by_name,
            modified_parameters_set,
        )

        # Check and see if the incoming connection is from an agent. If so, we'll hide the model parameter
        if target_parameter.name == "agent":
            self.hide_parameter_by_name("model")
            modified_parameters_set.add("model")

        if target_parameter.name == "model":
            self.hide_parameter_by_name("agent")
            modified_parameters_set.add("agent")

            # Check and see if the incoming connection is from a prompt model config
            # If it is, we'll set the model parameter to the incoming connection
            if source_parameter.name == "prompt_model_config":
                logger.info(f"Incoming connection from {source_node.name} to {self.name}")
                target_parameter._type = "Prompt Model Config"
                target_parameter.remove_trait(trait_type=target_parameter.find_elements_by_type(Options)[0])

                modified_parameters_set.add("model")

        return super().after_incoming_connection(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,
        source_parameter: Parameter,
        target_parameter: Parameter,
        modified_parameters_set: set[str],
    ) -> None:
        # Check and see if the incoming connection is from an agent. If so, we'll hide the model parameter
        if target_parameter.name == "agent":
            self.show_parameter_by_name("model")
            modified_parameters_set.add("model")

        if target_parameter.name == "model":
            self.show_parameter_by_name("agent")
            modified_parameters_set.add("agent")

            target_parameter._type = "str"
            target_parameter.add_trait(Options(choices=MODEL_CHOICES))
            target_parameter.set_default_value(DEFAULT_MODEL)
            target_parameter.default_value = DEFAULT_MODEL
            self.set_parameter_value("model", DEFAULT_MODEL)
            modified_parameters_set.add("model")
        return super().after_incoming_connection_removed(
            source_node, source_parameter, target_parameter, modified_parameters_set
        )

    def process(self) -> AsyncResult[Structure]:
        # Get the parameters from the node
        params = self.parameter_values
        agent_dict = self.get_parameter_value("agent")
        model = self.get_parameter_value("model")

        # If an agent is provided, we'll use that.
        # If a prompt model config is provided to the _agent_ parameter, we'll create an agent and use that.
        # If nothing is connected to an agent, check and see if a prompt model config is connected to the model parameter
        # If it is, we'll create an agent and use that.
        # If nothing is connected to the agent or model parameter, we'll create a new agent with a default prompt driver
        default_prompt_driver = GriptapeCloudPromptDriver(
            model=DEFAULT_MODEL,
            api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR),
            stream=True,
        )

        if isinstance(agent_dict, dict):
            logger.info(f"Agent dict: {agent_dict}")
            agent = Agent.from_dict(agent_dict)

            # make sure the agent is using a PromptTask
            if not isinstance(agent.tasks[0], PromptTask):
                agent.add_task(PromptTask(prompt_driver=default_prompt_driver))
        elif isinstance(agent_dict, BasePromptDriver):
            agent = Agent(prompt_driver=agent_dict)
        else:
            if isinstance(model, str):
                logger.info(f"Model is a string: {model}")
                prompt_driver = GriptapeCloudPromptDriver(
                    model=model,
                    api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR),
                    stream=True,
                )
            else:
                logger.info(f"Model is from a prompt driver: {model}")
                prompt_driver = model

            agent = Agent(prompt_driver=prompt_driver)

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
