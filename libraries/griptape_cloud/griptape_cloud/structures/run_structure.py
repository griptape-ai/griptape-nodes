import logging
from typing import TYPE_CHECKING, Any, cast

from griptape_cloud_client.types import Unset

from griptape_cloud.base.base_griptape_cloud_node import BaseGriptapeCloudNode
from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterList, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

if TYPE_CHECKING:
    from griptape_cloud_client.models.structure_detail import StructureDetail

logger = logging.getLogger("griptape_nodes")
logger.setLevel(logging.INFO)


class RunStructure(BaseGriptapeCloudNode, ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="structure",
                input_types=["StructureDetail"],
                type="StructureDetail",
                output_type="StructureDetail",
                default_value=None,
                tooltip="The structure to run",
                allowed_modes={ParameterMode.INPUT},
            )
        )

        self.add_parameter(
            ParameterList(
                name="args",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value=None,
                tooltip="The arguments to pass to the structure run",
            )
        )

        self.add_parameter(
            Parameter(
                name="structure_run_id",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value=None,
                tooltip="The ID of the structure run",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="output",
                output_type="dict",
                default_value=None,
                tooltip="The output of the structure run",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        with ParameterGroup(name="Events") as events_group:
            Parameter(name="include_events", type="bool", default_value=False, tooltip="Include events details.")

            Parameter(
                name="events",
                type="str",
                tooltip="Displays processing events if enabled.",
                ui_options={"multiline": True, "placeholder_text": "Events"},
                allowed_modes={ParameterMode.OUTPUT},
            )
        events_group.ui_options = {"hide": True}  # Hide the events group by default.
        self.add_node_element(events_group)

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_workflow_run() or []

        try:
            if not self.get_parameter_value("structure"):
                msg = "Structure is not set. Configure the Node with a valid Griptape Cloud Structure before running."
                exceptions.append(ValueError(msg))

            structure = cast("StructureDetail", self.get_parameter_value("structure"))

            deployment = self._get_deployment(structure.latest_deployment_id)
            if not self._is_deployment_ready(deployment):
                msg = f"Structure '{structure.name}' is not ready. Deployment status: {deployment.status}"
                exceptions.append(ValueError(msg))

        except Exception as e:
            # Add any exceptions to your list to return
            exceptions.append(e)

        # if there are exceptions, they will display when the user tries to run the flow with the node.
        return exceptions if exceptions else None

    def _process(self) -> None:
        include_events = self.get_parameter_value("include_events")
        structure = cast("StructureDetail", self.get_parameter_value("structure"))
        args = self.get_parameter_value("args")
        structure_run = self._create_structure_run(structure_id=structure.structure_id, args=args)

        output: Any | None = None

        for events in self._poll_structure_run_events(structure_run_id=structure_run.structure_run_id):
            if include_events:
                self.append_value_to_parameter("events", "\n".join(str(event.payload) for event in events))

        structure_run = self._get_structure_run(structure_run_id=structure_run.structure_run_id)
        output = structure_run.output if not isinstance(structure_run.output, Unset) else None
        self.parameter_output_values["output"] = output

    def process(
        self,
    ) -> AsyncResult[None]:
        yield lambda: self._process()
