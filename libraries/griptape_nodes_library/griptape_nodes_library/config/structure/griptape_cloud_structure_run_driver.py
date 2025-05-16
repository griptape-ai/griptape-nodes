import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpx
from httpx import Response

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
from griptape_nodes.traits.options import Options
from griptape_nodes_library.config.structure.base_structure_run_driver import BaseStructureRunDriver
from griptape_nodes_library.config.structure.gt_structure_run_drivers import GtGriptapeCloudStructureRunDriver

# --- Constants ---

SERVICE = "Griptape"
DEFAULT_STRUCTURE_BASE_ENDPOINT = "https://cloud.griptape.ai"
API_KEY_URL = "https://cloud.griptape.ai/configuration/api-keys"
API_KEY_ENV_VAR = "GT_CLOUD_API_KEY"
GT_CLOUD_BASE_URL_ENV_VAR = "GT_CLOUD_BASE_URL"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass(eq=False)
class StructureOptions(Options):
    choices_value_lookup: dict[str, Any] = field(kw_only=True)

    def converters_for_trait(self) -> list[Callable]:
        def converter(value: Any) -> Any:
            if value not in self.choices:
                msg = f"Selection '{value}' is not in choices. Defaulting to first choice: '{self.choices[0]}'."
                logger.warning(msg)
                value = self.choices[0]
            value = self.choices_value_lookup.get(value, self.choices[0])["structure_id"]
            msg = f"Converted choice into value: {value}"
            logger.warning(msg)
            return value

        return [converter]

    def validators_for_trait(self) -> list[Callable[[Parameter, Any], Any]]:
        def validator(param: Parameter, value: Any) -> None:
            if value not in [x.get("structure_id") for x in self.choices_value_lookup.values()]:
                msg = f"Attempted to set Parameter '{param.name}' to value '{value}', but that was not one of the available choices."

                def raise_error() -> None:
                    raise ValueError(msg)

                raise_error()

        return [validator]


class GriptapeCloudStructureRun(BaseStructureRunDriver):
    """Node for Griptape Cloud Structure Run Driver.

    This node creates an Griptape Cloud structure run driver and outputs its configuration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.base_url = self.get_config_value(SERVICE, GT_CLOUD_BASE_URL_ENV_VAR)
        self.structures = self._get_structure_options()
        self.choices = list(map(GriptapeCloudStructureRun._structure_to_name_and_id, self.structures))

        # Add additional parameters specific to Griptape Cloud
        self.add_parameter(
            Parameter(
                name="structure_id",
                default_value=(self.structures[0]["structure_id"] if self.structures else None),
                input_types=["str"],
                output_type="str",
                type="str",
                traits={
                    StructureOptions(
                        choices=list(map(GriptapeCloudStructureRun._structure_to_name_and_id, self.structures)),
                        choices_value_lookup={
                            GriptapeCloudStructureRun._structure_to_name_and_id(s): s for s in self.structures
                        },
                    )
                },
                allowed_modes={
                    ParameterMode.INPUT,
                    ParameterMode.OUTPUT,
                    ParameterMode.PROPERTY,
                },
                tooltip="structure",
            )
        )

        # Group for less commonly used configuration options.
        with ParameterGroup(name="Advanced options") as advanced_group:
            Parameter(
                name="async_run",
                input_types=["bool"],
                output_type="bool",
                type="bool",
                default_value=False,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Run the structure run asynchronously.",
            )
            Parameter(
                name="structure_run_wait_time_interval",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=2,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Wait time interval in seconds for the structure run to complete.",
            )
            Parameter(
                name="structure_run_max_wait_time_attempts",
                input_types=["int"],
                output_type="int",
                type="int",
                default_value=20,
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                tooltip="Maximum wait time attempts for the structure run to complete.",
            )

        advanced_group.ui_options = {"hide": True}  # Hide the advanced group by default.
        self.add_node_element(advanced_group)

    @classmethod
    def _structure_to_name_and_id(cls, structure: dict[str, Any]) -> str:
        return f"{structure['name']} ({structure['structure_id']})"

    def _get_headers(self) -> dict[str, str]:
        api_key = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _get_structure_options(self) -> list[dict[str, Any]]:
        try:
            list_structures_response = self._list_structures()
            data = list_structures_response.json()
            return data.get("structures", [])
        except Exception:
            return []

    def _list_structures(self) -> Response:
        httpx_client = httpx.Client(base_url=self.base_url)
        url = urljoin(
            self.base_url,
            "/api/structures",
        )
        response = httpx_client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response

    def _get_structure(self) -> Response:
        httpx_client = httpx.Client(base_url=self.base_url)
        structure_id = self.get_parameter_value("structure_id")
        url = urljoin(
            self.base_url,
            f"/api/structures/{structure_id}",
        )
        response = httpx_client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response

    def _get_deployment(self, deployment_id: str) -> Response:
        httpx_client = httpx.Client(base_url=self.base_url)
        url = urljoin(
            self.base_url,
            f"/api/deployments/{deployment_id}",
        )
        response = httpx_client.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response

    def process(self) -> None:
        # Get the parameters from the node
        params = self.parameter_values

        # --- Get Common Driver Arguments ---
        # Use the helper method from BaseImageDriver to get common driver arguments
        common_args = self._get_common_driver_args(params)

        # --- Prepare Griptape Cloud Specific Arguments ---
        specific_args = {}

        # Retrieve the mandatory API key.
        specific_args["api_key"] = self.get_config_value(service=SERVICE, value=API_KEY_ENV_VAR)
        specific_args["base_url"] = self.get_config_value(service=SERVICE, value=GT_CLOUD_BASE_URL_ENV_VAR)
        specific_args["structure_id"] = self.get_parameter_value("structure_id")
        specific_args["structure_run_wait_time_interval"] = self.get_parameter_value("structure_run_wait_time_interval")
        specific_args["structure_run_max_wait_time_attempts"] = self.get_parameter_value(
            "structure_run_max_wait_time_attempts"
        )
        specific_args["async_run"] = self.get_parameter_value("async_run")

        all_kwargs = {**common_args, **specific_args}

        self.parameter_output_values["structure_run_config"] = GtGriptapeCloudStructureRunDriver(**all_kwargs)

    def validate_before_workflow_run(self) -> list[Exception] | None:
        """Validates that the Griptape Cloud API key is configured correctly and that the structure is valid.

        Calls the base class helper `_validate_api_key` with Griptape-specific
        configuration details. Also checks that the structure ID is set and that the
        structure has a latest deployment that is in the "SUCCEEDED" status.
        """
        exceptions = []
        api_key_exceptions = self._validate_api_key(
            service_name=SERVICE,
            api_key_env_var=API_KEY_ENV_VAR,
            api_key_url=API_KEY_URL,
        )
        if api_key_exceptions:
            # If we don't have a valid API key, we can't proceed
            return api_key_exceptions

        try:
            if not self.get_parameter_value("structure_id"):
                msg = "Structure ID is not set. Configure the Node with a valid structure ID before running."
                exceptions.append(ValueError(msg))

            structure = self._get_structure()
            structure_details = structure.json()

            if (latest_deployment_id := structure_details.get("latest_deployment", None)) is None:
                msg = f"Structure ID {self.get_parameter_value('structure_id')} does not have a latest deployment. Please check the Griptape Cloud Structure for more details."
                exceptions.append(ValueError(msg))
            else:
                deployment = self._get_deployment(latest_deployment_id)
                deployment_details = deployment.json()
                if (deployment_status := deployment_details.get("status", None)) != "SUCCEEDED":
                    msg = f"Structure ID {self.get_parameter_value('structure_id')} has a latest deployment with ID {latest_deployment_id} that is in status: {deployment_status}. Please check the Griptape Cloud Structure for more details."
                    exceptions.append(ValueError(msg))

        except Exception as e:
            # Add any exceptions to your list to return
            exceptions.append(e)
