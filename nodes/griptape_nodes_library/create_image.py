from griptape.drivers.image_generation.openai import OpenAiImageGenerationDriver
from griptape.structures.agent import Agent
from griptape.tasks import PromptImageGenerationTask

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
import openai
from griptape_nodes_library.utils.error_utils import try_throw_error

API_KEY_ENV_VAR = "OPENAI_API_KEY"
SERVICE = "OpenAI"
DEFAULT_MODEL = "dall-e-3"
DEFAULT_QUALITY = "hd"
DEFAULT_STYLE = "natural"


class gnCreateImage(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.config = GriptapeNodes.ConfigManager()

        self.category = "Agent"
        self.description = "Generate an image"

        self.add_parameter(
            Parameter(
                name="agent",
                allowed_types=["Agent"],
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.INPUT, ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="prompt",
                allowed_types=["str"],
                tooltip="None",
                default_value="",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        self.add_parameter(
            Parameter(
                name="driver",
                allowed_types=["BaseImageGenerationDriver"],
                tooltip="None",
                default_value="",
            )
        )

        self.add_parameter(
            Parameter(
                name="output",
                allowed_types=["ImageArtifact"],
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="output_file",
                allowed_types=["str"],
                tooltip="None",
                default_value=None,
            )
        )

        self.add_parameter(
            Parameter(
                name="output_dir",
                allowed_types=["str"],
                tooltip="None",
                default_value=None,
            )
        )

    def validate_node(self) -> list[Exception] | None:
        # TODO(kate): Figure out how to wrap this so it's easily repeatable
        exceptions = []
        api_key = self.getenv(SERVICE,API_KEY_ENV_VAR)
        # No need for the api key. These exceptions caught on other nodes.
        if self.parameter_values.get("agent", None) and self.parameter_values.get("driver", None):
            return None
        if not api_key:
            msg=f"{API_KEY_ENV_VAR} is not defined"
            exceptions.append(KeyError(msg))
            return exceptions
        try:
            client = openai.OpenAI(api_key=api_key)
            client.models.list()
        except openai.AuthenticationError as e:
            exceptions.append(e)
        return exceptions if exceptions else None

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        workspace_path = self.config.workspace_path
        images_dir = workspace_path / "Images/"

        agent = params.get("agent", Agent(stream=True))
        prompt = params.get("prompt", "")

        # Initialize driver kwargs with required parameters
        kwargs = {}

        # Driver
        driver_val = params.get("driver", None)
        if driver_val:
            driver = driver_val
        else:
            driver = OpenAiImageGenerationDriver(
                model=params.get("model", DEFAULT_MODEL),
                api_key=self.getenv(service=SERVICE, value=API_KEY_ENV_VAR),
            )
        kwargs["image_generation_driver"] = driver

        # Declaring a prio towards file, not dir for now, at least
        out_file = params.get("output_file", None)
        if out_file:
            kwargs["output_file"] = out_file
            print(rf'\Generating "{out_file}"')
        else:
            out_dir = params.get("output_dir", None)
            if out_dir:
                kwargs["output_dir"] = out_dir
                print(f'\nLook for image in "{out_dir}"')
            else:
                kwargs["output_dir"] = images_dir
                print(f'\nLook for image in "{images_dir}"')

        # Add the actual image gen *task
        agent.add_task(PromptImageGenerationTask(**kwargs))

        # Run the agent
        result = agent.run(prompt)
        self.parameter_output_values["output"] = result.output
        try_throw_error(agent.output)
        # Reset the agent
        agent._tasks = []
