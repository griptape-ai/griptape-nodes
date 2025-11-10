import logging
from typing import Any

from griptape_cloud.publish_workflow.parameters.griptape_cloud_structure_config_parameter import (
    GriptapeCloudStructureConfigParameter,
)
from griptape_cloud.publish_workflow.parameters.griptape_cloud_webhook_config_parameter import (
    GriptapeCloudWebhookConfigParameter,
)
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import StartNode

logger = logging.getLogger(__name__)


class GriptapeCloudStartFlow(StartNode):
    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        if metadata is None:
            metadata = {}
        metadata["showaddparameter"] = True
        super().__init__(name, metadata)

        hide_structure_config = metadata.get("hide_structure_config", False)
        structure_id = metadata.get("structure_id")
        hide_structure_id = metadata.get("hide_structure_id")
        integration_id = metadata.get("integration_id")
        hide_integration_details = metadata.get("hide_integration_details")

        if hide_structure_id is None:
            hide_structure_id = structure_id is None
        if hide_integration_details is None:
            hide_integration_details = integration_id is None

        # Add structure config group
        self._structure_config_params = GriptapeCloudStructureConfigParameter(
            self,
            metadata=metadata,
            allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            hide_structure_config=hide_structure_config,
            hide_structure_id=hide_structure_id,
        )

        # Add webhook config group
        self._webhook_config_params = GriptapeCloudWebhookConfigParameter(
            self,
            metadata=metadata,
            allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
            hide_integration_details=hide_integration_details,
        )
        self._webhook_config_params.set_webhook_config_param_visibility(visible=False)

    @classmethod
    def get_default_node_parameter_names(cls) -> list[str]:
        """Get the names of the parameters configured on the node by default."""
        params = []
        params.extend(GriptapeCloudStructureConfigParameter.get_param_names())
        params.extend(GriptapeCloudWebhookConfigParameter.get_param_names())
        params.extend(["was_successful", "result_details"])
        params.extend(["exec_in", "exec_out", "failed"])
        return params

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        if parameter.name == "enable_webhook_integration":
            self._webhook_config_params.set_webhook_config_param_visibility(visible=value)

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_workflow_run() or []
        return exceptions if exceptions else None

    def process(self) -> None:
        pass
