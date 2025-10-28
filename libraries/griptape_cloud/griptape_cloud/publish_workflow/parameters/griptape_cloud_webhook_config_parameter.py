from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMessage, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode


class GriptapeCloudWebhookConfigParameter:
    def __init__(
        self,
        node: BaseNode,
        metadata: dict[Any, Any] | None = None,
        allowed_modes: set[ParameterMode] | None = None,
        *,
        hide_integration_id: bool = False,
    ) -> None:
        self.node = node
        if metadata is None:
            metadata = {}
        self.allowed_modes = allowed_modes

        integration_id = metadata.get("integration_id")

        # Add webhook config group
        with ParameterGroup(name="Webhook Config") as webhook_config_group:
            Parameter(
                name="enable_webhook_integration",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                default_value=False,
                tooltip="Whether to enable a webhook integration for the Structure.",
                allowed_modes=allowed_modes,
            )
            Parameter(
                name="integration_id",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=integration_id,
                tooltip="The integration ID of the published workflow",
                hide=hide_integration_id,
                allowed_modes=allowed_modes,
            )
            ParameterMessage(
                name="griptape_cloud_webhook_config_parameter_message",
                title="Griptape Cloud Webhook Configuration Notice",
                variant="info",
                value=self.get_webhook_config_message(),
                ui_options={"hide": True},
            )
            Parameter(
                name="payload",
                input_types=["json", "str", "dict"],
                type="json",
                default_value=None,
                tooltip="The payload for the webhook integration.",
                ui_options={
                    "display_name": "Webhook Payload",
                },
                allowed_modes=allowed_modes,
            )
            Parameter(
                name="query_params",
                input_types=["json", "str", "dict"],
                type="json",
                default_value=None,
                tooltip="The query parameters for the webhook integration.",
                ui_options={
                    "display_name": "Webhook Query Params",
                },
                allowed_modes=allowed_modes,
            )
            Parameter(
                name="headers",
                input_types=["json", "str", "dict"],
                type="json",
                default_value=None,
                tooltip="The headers for the webhook integration.",
                ui_options={
                    "display_name": "Webhook Headers",
                },
                allowed_modes=allowed_modes,
            )

        webhook_config_group.ui_options = {"collapsed": True}
        node.add_node_element(webhook_config_group)

    @classmethod
    def get_param_names(cls) -> list[str]:
        return [
            "enable_webhook_integration",
            "integration_id",
            "griptape_cloud_webhook_config_parameter_message",
            "payload",
            "query_params",
            "headers",
        ]

    def get_webhook_config_message(self) -> str:
        return (
            "The Griptape Cloud Webhook Integration configures your published workflow with a Webhook Integration to invoke the Structure.\n\n "
            "With this mode enabled, you should:\n"
            "   1. Configure your Workflow to expect input directly from the Webhook, making use of the appropriate parameters:\n"
            "      - 'payload' for the webhook body\n"
            "      - 'query_params' for the webhook query parameters\n"
            "      - 'headers' for the webhook headers\n"
            "   2. Click the 'Publish' button (rocket icon, top right) to publish the workflow to Griptape Cloud\n"
            "   3. Utilize the Webhook Integration URL in Griptape Cloud as the target for your Webhook\n\n"
        )

    def set_webhook_config_param_visibility(self, *, visible: bool) -> None:
        params = self.get_param_names()
        params.remove("enable_webhook_integration")  # Always show this param
        params.remove("integration_id")  # Handled separately
        params.remove("griptape_cloud_webhook_config_parameter_message")  # Handled separately
        for param in params:
            if visible:
                self.node.show_parameter_by_name(param)
                self.node.show_message_by_name("griptape_cloud_webhook_config_parameter_message")
            else:
                self.node.hide_parameter_by_name(param)
                self.node.hide_message_by_name("griptape_cloud_webhook_config_parameter_message")
