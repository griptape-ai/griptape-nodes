from typing import Any

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes.traits.options import Options


class CreateSchemaField(DataNode):
    """Create a schema field definition.

    This node defines a single field for a Pydantic schema, with a name,
    type, and optional description. Multiple schema fields can be connected
    to a Create Schema node to build a complete schema.
    """

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Field name parameter
        self.add_parameter(
            Parameter(
                name="field_name",
                type="str",
                default_value="",
                tooltip="Name of the field in the schema",
                allowed_modes={ParameterMode.PROPERTY},
            )
        )

        # Field type parameter
        self.add_parameter(
            Parameter(
                name="field_type",
                type="str",
                default_value="str",
                tooltip="Type for the field (str, int, float, bool, list, dict)",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=["str", "int", "float", "bool", "list", "dict"])},
            )
        )

        # Field description parameter
        self.add_parameter(
            Parameter(
                name="field_description",
                type="str",
                default_value="",
                tooltip="Description for the field (optional)",
                allowed_modes={ParameterMode.PROPERTY},
                ui_options={"multiline": True},
            )
        )

        # Output parameter - the field definition as a dict
        self.add_parameter(
            Parameter(
                name="schema_field",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="dict",
                default_value={},
                tooltip="Schema field definition",
                ui_options={"hide_property": True},
            )
        )

    def process(self) -> None:
        """Process the node by creating a field definition dictionary."""
        field_name = self.get_parameter_value("field_name")
        field_type = self.get_parameter_value("field_type")
        field_description = self.get_parameter_value("field_description")

        # Create the field definition dictionary
        field_def = {
            "name": str(field_name) if field_name else "",
            "type": str(field_type) if field_type else "str",
            "description": str(field_description) if field_description else "",
        }

        self.parameter_output_values["schema_field"] = field_def
