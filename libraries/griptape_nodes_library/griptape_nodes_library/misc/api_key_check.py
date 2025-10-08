from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMessage
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, logger


class ApiCheck(BaseNode):
    """TODO (jason): Test once this is resolved: https://github.com/griptape-ai/griptape-nodes/issues/1309."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.add_node_element(
            ParameterMessage(
                name="message",
                title="What is this node?",
                variant="info",
                value="This node demonstrates how you can display a warning to the user about setting an API key.",
            )
        )

        self.add_parameter(
            Parameter(
                name="hide_messages",
                type="bool",
                default_value=False,
                tooltip="This is a test parameter",
            )
        )

        self.add_parameter(
            Parameter(
                name="test_parameter",
                type="str",
                default_value="This is a test parameter to see if it toggles on and off.",
                tooltip="This is a test parameter",
            )
        )
        self.add_node_element(
            ParameterMessage(
                name="api_key_message",
                title="API Key Required",
                variant="warning",
                value="This node requires an EXA_API_KEY to function.\n\nPlease set the key in your Griptape Settings.",
            )
        )
        # self.clear_api_key_check() #TODO(jason): Test once this is resolved: https://github.com/griptape-ai/griptape-nodes/issues/1309  # noqa: ERA001

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        if parameter.name == "hide_messages":
            # If the hide_messages parameter is set to True, we want to show the message
            if value:
                self.hide_parameter_by_name("test_parameter")
                self.hide_message_by_name("api_key_message")
            else:
                self.show_parameter_by_name("test_parameter")
                self.show_message_by_name("api_key_message")

        return super().after_value_set(parameter, value)

    def clear_api_key_check(self) -> bool:
        # Check to see if the API key is set, if not we'll show the message
        message_name = "api_key_message"
        api_key = GriptapeNodes.SecretsManager().get_secret("EXA_API_KEY")
        if api_key:
            self.hide_message_by_name(message_name)
            logger.info("Found it")
            return True
        self.show_message_by_name(message_name)
        logger.info("Not found")
        return False

    def process(self) -> None:
        self.clear_api_key_check()
