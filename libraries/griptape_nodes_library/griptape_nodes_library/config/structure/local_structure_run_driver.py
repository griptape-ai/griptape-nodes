import logging

from griptape.drivers.prompt.griptape_cloud_prompt_driver import GriptapeCloudPromptDriver
from griptape.structures import Agent as gtAgent

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes_library.config.structure.base_structure_run_driver import BaseStructureRunDriver
from griptape_nodes_library.config.structure.gt_structure_run_drivers import GtLocalStructureRunDriver

API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
API_KEY_URL = "https://cloud.griptape.ai/configuration/api-keys"
SERVICE = "Griptape"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class LocalStructureRun(BaseStructureRunDriver):
    """Node for Local Structure Run Driver.

    This node creates an Local structure run driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Add additional parameters specific to LocalStructureRun
        self.add_parameter(
            Parameter(
                name="agent",
                type="Agent",
                input_types=["Agent"],
                tooltip="None",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
            )
        )

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # --- Prepare Local Structure Run Specific Arguments ---
        specific_args = {}

        agent = params.get("agent")
        if not agent:
            prompt_driver = GriptapeCloudPromptDriver(
                model="gpt-4.1",
                api_key=self.get_config_value(SERVICE, API_KEY_ENV_VAR),
            )
            agent = gtAgent(prompt_driver=prompt_driver)
        elif type(agent) is dict:
            agent = gtAgent.from_dict(agent)

        specific_args["create_structure"] = lambda: agent

        self.parameter_output_values["structure_run_config"] = GtLocalStructureRunDriver(**specific_args)

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validates that the Griptape Cloud API key is configured correctly.

        Calls the base class helper `_validate_api_key` with Griptape-specific
        configuration details.
        """
        return self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=API_KEY_ENV_VAR,
            api_key_url=API_KEY_URL,
        )
