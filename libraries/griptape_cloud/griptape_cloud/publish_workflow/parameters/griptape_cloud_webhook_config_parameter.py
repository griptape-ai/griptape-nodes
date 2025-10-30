from typing import Any
from urllib.parse import urljoin

from griptape_cloud.base.base_griptape_cloud_node import DEFAULT_GRIPTAPE_CLOUD_URL
from griptape_nodes.exe_types.core_types import (
    NodeMessageResult,
    Parameter,
    ParameterMessage,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.secrets_events import GetSecretValueRequest, GetSecretValueResultSuccess
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.button import (
    Button,
    ButtonDetailsMessagePayload,
    ModalContentPayload,
    OnClickMessageResultPayload,
)


class GriptapeCloudWebhookConfigParameter:
    def __init__(
        self,
        node: BaseNode,
        metadata: dict[Any, Any] | None = None,
        allowed_modes: set[ParameterMode] | None = None,
        *,
        hide_integration_details: bool = False,
    ) -> None:
        self.node = node
        if metadata is None:
            metadata = {}
        self.allowed_modes = allowed_modes

        integration_id = metadata.get("integration_id")

        # Add webhook config parameters
        node.add_parameter(
            Parameter(
                name="enable_webhook_integration",
                input_types=["bool"],
                type="bool",
                output_type="bool",
                default_value=False,
                tooltip="Whether to enable a webhook integration for the Structure.",
                allowed_modes=allowed_modes,
            )
        )
        node.add_parameter(
            Parameter(
                name="webhook_url",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="",
                tooltip="The webhook URL for the published workflow",
                hide=hide_integration_details,
                allowed_modes={ParameterMode.PROPERTY},
                traits={
                    Button(
                        icon="webhook", on_click=self._handle_get_webhook_url, tooltip="Get Webhook URL", state="normal"
                    ),
                },
            )
        )
        node.add_parameter(
            Parameter(
                name="integration_id",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=integration_id,
                tooltip="The integration ID of the published workflow",
                hide=hide_integration_details,
                allowed_modes=allowed_modes,
                traits={
                    Button(
                        icon="link",
                        on_click=self._handle_integration_link,
                        tooltip="View Integration in Griptape Cloud",
                    ),
                },
            )
        )
        node.add_node_element(
            ParameterMessage(
                name="griptape_cloud_webhook_config_parameter_message",
                title="Griptape Cloud Webhook Configuration Notice",
                variant="info",
                value=self.get_webhook_config_message(),
                ui_options={"hide": True},
            )
        )
        node.add_parameter(
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
        )
        node.add_parameter(
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
        )
        node.add_parameter(
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
        )

    @classmethod
    def get_param_names(cls) -> list[str]:
        return [
            "enable_webhook_integration",
            "webhook_url",
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
        params.remove("webhook_url")  # Handled separately
        params.remove("integration_id")  # Handled separately
        params.remove("griptape_cloud_webhook_config_parameter_message")  # Handled separately
        for param in params:
            if visible:
                self.node.show_parameter_by_name(param)
                self.node.show_message_by_name("griptape_cloud_webhook_config_parameter_message")
            else:
                self.node.hide_parameter_by_name(param)
                self.node.hide_message_by_name("griptape_cloud_webhook_config_parameter_message")

    def _handle_integration_link(
        self,
        button: Button,  # noqa: ARG002
        button_details: ButtonDetailsMessagePayload,
    ) -> NodeMessageResult | None:
        integration_id = self.node.get_parameter_value("integration_id")
        if integration_id:
            integration_url = urljoin(DEFAULT_GRIPTAPE_CLOUD_URL, f"/integrations/{integration_id}")
            return NodeMessageResult(
                success=True,
                details="Webhook URL retrieved successfully.",
                response=OnClickMessageResultPayload(
                    button_details=button_details,
                    href=integration_url,
                ),
                altered_workflow_state=False,
            )
        return None

    def _handle_get_webhook_url(self, button: Button, button_details: ButtonDetailsMessagePayload) -> NodeMessageResult:  # noqa: ARG002
        integration_id = self.node.get_parameter_value("integration_id")

        # If webhook URL doesn't exist yet, provide helpful message
        if not integration_id:
            clipboard_copyable_content = (
                "No webhook URL available yet. Please publish the workflow to Griptape Cloud first."
            )
        else:
            get_secret_value_request = GetSecretValueRequest(key="GT_CLOUD_API_KEY")
            result = GriptapeNodes.handle_request(get_secret_value_request)
            if not isinstance(result, GetSecretValueResultSuccess):
                details = "Failed to retrieve API key from secrets manager."
                raise RuntimeError(details)
            webhook_url = urljoin(DEFAULT_GRIPTAPE_CLOUD_URL, f"/api/integrations/{integration_id}/handler")
            webhook_url = f"{webhook_url}?api_key={result.value}"
            clipboard_copyable_content = webhook_url

        # Return response with button state and modal content
        return NodeMessageResult(
            success=True,
            details="Webhook URL retrieved successfully.",
            response=OnClickMessageResultPayload(
                button_details=button_details,
                modal_content=ModalContentPayload(
                    clipboard_copyable_content=clipboard_copyable_content,
                    title="Webhook URL",
                ),
            ),
            altered_workflow_state=False,
        )
