from typing import Any
from urllib.parse import urljoin

from griptape_cloud.base.base_griptape_cloud_node import DEFAULT_GRIPTAPE_CLOUD_URL
from griptape_nodes.exe_types.core_types import NodeMessageResult, Parameter, ParameterGroup, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.traits.button import Button, ButtonDetailsMessagePayload, OnClickMessageResultPayload


class GriptapeCloudStructureConfigParameter:
    def __init__(
        self,
        node: BaseNode,
        metadata: dict[Any, Any] | None = None,
        allowed_modes: set[ParameterMode] | None = None,
        *,
        hide_structure_config: bool = False,
        hide_structure_id: bool = False,
    ) -> None:
        self.node = node
        if metadata is None:
            metadata = {}
        metadata["showaddparameter"] = True
        structure_id = metadata.get("structure_id")
        structure_name = metadata.get("structure_name")
        structure_description = metadata.get("structure_description")

        # Add structure config group
        with ParameterGroup(name="Structure Config") as structure_config_group:
            Parameter(
                name="structure_id",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=structure_id,
                tooltip="The structure ID of the published workflow",
                hide=hide_structure_id,
                allowed_modes=allowed_modes,
                traits={
                    Button(
                        icon="link",
                        on_click=self._handle_structure_link,
                        tooltip="View Structure in Griptape Cloud",
                    )
                },
            )
            Parameter(
                name="structure_name",
                input_types=["str"],
                type="str",
                default_value=structure_name,
                output_type="str",
                tooltip="The name for the Griptape Cloud Structure.",
                allowed_modes=allowed_modes,
            )
            Parameter(
                name="structure_description",
                input_types=["str"],
                type="str",
                default_value=structure_description,
                output_type="str",
                tooltip="The description for the Griptape Cloud Structure.",
                allowed_modes=allowed_modes,
            )

        structure_config_group.ui_options = {"hide": hide_structure_config}
        self.node.add_node_element(structure_config_group)

    @classmethod
    def get_param_names(cls) -> list[str]:
        return [
            "structure_id",
            "structure_name",
            "structure_description",
        ]

    def _handle_structure_link(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult | None:
        structure_id = self.node.get_parameter_value("structure_id")
        if structure_id:
            structure_url = urljoin(DEFAULT_GRIPTAPE_CLOUD_URL, f"/structures/{structure_id}")
            return NodeMessageResult(
                success=True,
                details="Webhook URL retrieved successfully.",
                response=OnClickMessageResultPayload(
                    button_details=button_details,
                    href=structure_url,
                ),
                altered_workflow_state=False,
            )
        return None
