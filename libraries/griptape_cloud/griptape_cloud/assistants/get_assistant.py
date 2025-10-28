import logging
from typing import Any

from griptape_cloud.assistants.assistant_options import AssistantOptions
from griptape_cloud.base.base_griptape_cloud_node import BaseGriptapeCloudNode
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode

logger = logging.getLogger("griptape_nodes")
logger.setLevel(logging.INFO)


class GetAssistant(BaseGriptapeCloudNode, DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.assistants = self._list_assistants().assistants
        self.choices = list(map(AssistantOptions._assistant_to_name_and_id, self.assistants))

        self.add_parameter(
            Parameter(
                name="assistant_id",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value=self.assistants[0].assistant_id if self.assistants else None,
                traits={
                    AssistantOptions(
                        choices=self.choices,
                        choices_value_lookup={
                            AssistantOptions._assistant_to_name_and_id(s): s for s in self.assistants
                        },
                    )
                },
                tooltip="The ID of the assistant",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="name",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=None,
                tooltip="The name of the assistant",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="assistant",
                input_types=["AssistantDetail"],
                type="AssistantDetail",
                output_type="AssistantDetail",
                default_value=None,
                tooltip="The assistant",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_workflow_run() or []

        try:
            if not self.get_parameter_value("assistant_id"):
                msg = "Assistant ID is not set. Configure the Node with a valid Griptape Cloud Assistant ID before running."
                exceptions.append(ValueError(msg))

        except Exception as e:
            # Add any exceptions to your list to return
            exceptions.append(e)

        # if there are exceptions, they will display when the user tries to run the flow with the node.
        return exceptions if exceptions else None

    def after_value_set(
        self, parameter: Parameter, value: Any, modified_parameters_set: set[str] | None = None
    ) -> None:
        """Callback after a value has been set on this Node."""
        if parameter.name == "assistant_id" and value is not None:
            assistant = next((s for s in self.assistants if s.assistant_id == value), None)
            if assistant is None:
                msg = f"Assistant with ID '{value}' not found."
                logger.error(msg)
                raise ValueError(msg)
            self.set_parameter_value("assistant", assistant)
            self.set_parameter_value("name", assistant.name)
            if modified_parameters_set is not None:
                modified_parameters_set.add("assistant")
                modified_parameters_set.add("name")

    def process(self) -> None:
        pass
