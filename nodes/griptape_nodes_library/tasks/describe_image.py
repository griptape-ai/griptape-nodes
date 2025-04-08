from griptape.structures.agent import Agent
from griptape.tasks import PromptTask

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
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
                name="image",
                input_types=["ImageArtifact"],
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
            agent = Agent()
        else:
            agent = Agent().from_dict(agent)
        prompt = params.get("prompt", "")
        if prompt == "":
            prompt = "Describe the image"
        image_artifact = params.get("image", None)
        if image_artifact is None:
            self.parameter_output_values["output"] = "No image provided"
            return
        # Make sure the agent is using a PromptTask
        agent.add_task(PromptTask())

        # Run the agent

        result = agent.run([prompt, image_artifact])
        self.parameter_output_values["output"] = result.output.value
        try_throw_error(agent.output)
