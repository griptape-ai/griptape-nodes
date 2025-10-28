import logging
from typing import Any

from griptape_cloud.base.base_griptape_cloud_node import BaseGriptapeCloudNode
from griptape_cloud.structures.structure_options import StructureOptions
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode

logger = logging.getLogger("griptape_nodes")
logger.setLevel(logging.INFO)


class GetStructure(BaseGriptapeCloudNode, DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.structures = self._list_structures().structures
        self.choices = list(map(StructureOptions._structure_to_name_and_id, self.structures))

        self.add_parameter(
            Parameter(
                name="structure_id",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value=self.structures[0].structure_id if self.structures else None,
                traits={
                    StructureOptions(
                        choices=self.choices,
                        choices_value_lookup={
                            StructureOptions._structure_to_name_and_id(s): s for s in self.structures
                        },
                    )
                },
                tooltip="The ID of the structure",
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
                tooltip="The name of the structure",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="structure",
                input_types=["StructureDetail"],
                type="StructureDetail",
                output_type="StructureDetail",
                default_value=None,
                tooltip="The structure",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_workflow_run() or []

        try:
            if not self.get_parameter_value("structure_id"):
                msg = "Structure ID is not set. Configure the Node with a valid Griptape Cloud Structure ID before running."
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
        if parameter.name == "structure_id" and value is not None:
            structure = next((s for s in self.structures if s.structure_id == value), None)
            if structure is None:
                msg = f"Structure with ID '{value}' not found."
                logger.error(msg)
                raise ValueError(msg)
            self.set_parameter_value("structure", structure)
            self.set_parameter_value("name", structure.name)
            if modified_parameters_set is not None:
                modified_parameters_set.add("structure")
                modified_parameters_set.add("name")

    def process(self) -> None:
        pass
