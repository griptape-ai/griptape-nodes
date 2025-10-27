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
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )

        # Field type parameter - can be a string type or a nested schema dict
        self.add_parameter(
            Parameter(
                name="field_type",
                input_types=["str", "dict"],
                type="str",
                default_value="str",
                tooltip="Type for the field (str, int, float, bool, list, dict) or a nested schema dict",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )

        # List item type parameter - only visible when field_type is "list"
        self.add_parameter(
            Parameter(
                name="list_type",
                input_types=["str", "dict"],
                type="str",
                default_value="str",
                tooltip="Type of items in the list (str, int, float, bool, dict) or a nested schema dict",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                ui_options={"hide": True},
            )
        )

        # Field description parameter
        self.add_parameter(
            Parameter(
                name="field_description",
                type="str",
                default_value="",
                tooltip="Description for the field (optional)",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
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
            )
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide list_type."""
        if parameter.name == "field_type":
            list_type_param = self.get_parameter_by_name("list_type")
            if list_type_param:
                # Show list_type parameter only when field_type is "list"
                if value == "list":
                    self.show_parameter_by_name("list_type")
                else:
                    self.hide_parameter_by_name("list_type")

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        """Process the node by creating a field definition dictionary."""
        field_name = self.get_parameter_value("field_name")
        field_type = self.get_parameter_value("field_type")
        list_type = self.get_parameter_value("list_type")
        field_description = self.get_parameter_value("field_description")

        # Handle field_type - can be a string (simple type) or dict (nested schema)
        if isinstance(field_type, dict):
            # field_type is a nested schema dict - use it as-is
            type_value = field_type
        else:
            # field_type is a string - convert to string
            type_value = str(field_type) if field_type else "str"

        # Create the field definition dictionary
        field_def = {
            "name": str(field_name) if field_name else None,
            "type": type_value,
            "description": str(field_description) if field_description else None,
        }

        # Add list_type if field_type is "list"
        if type_value == "list" and list_type:
            # Handle list_type - can be a string or dict (nested schema)
            if isinstance(list_type, dict):
                field_def["list_type"] = list_type
            else:
                field_def["list_type"] = str(list_type)

        self.parameter_output_values["schema_field"] = field_def

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate that required parameters are set before running the node."""
        field_name = self.get_parameter_value("field_name")
        if not field_name:
            return [ValueError("Field name must be provided.")]
