from typing import Any

from pydantic import Field, create_model

from griptape_nodes.exe_types.core_types import (
    Parameter,
    ParameterList,
    ParameterMode,
)
from griptape_nodes.exe_types.node_types import DataNode
from griptape_nodes_library.utils.schema_utils import get_type


class CreateSchema(DataNode):
    """Create a Pydantic schema from field definitions.

    This node accepts a list of schema field definitions and converts them into
    a Pydantic BaseModel class that can be used for structured output validation.
    Connect Create Schema Field nodes to provide field definitions.
    """

    def __init__(
        self,
        name: str,
        metadata: dict[Any, Any] | None = None,
    ) -> None:
        super().__init__(name, metadata)

        # Schema name parameter
        self.add_parameter(
            Parameter(
                name="schema_name",
                type="str",
                default_value="DynamicSchema",
                tooltip="Name of the resulting JSON schema.",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Schema fields list - accepts dict inputs from Create Schema Field nodes
        self.add_parameter(
            ParameterList(
                name="schema_fields",
                input_types=["dict"],
                default_value=[],
                tooltip="List of schema field definitions",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Output parameter - the generated schema
        self.add_parameter(
            Parameter(
                name="schema",
                allowed_modes={ParameterMode.OUTPUT},
                output_type="dict",
                default_value=None,
                tooltip="The JSON schema",
            )
        )

    def _convert_type_string(self, type_str: str) -> type:
        """Convert type string to actual Python type.

        Args:
            type_str: String representation of type (e.g., "str", "int", "float")

        Returns:
            The corresponding Python type
        """
        type_mapping = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
        }

        type_str_lower = type_str.lower().strip()
        if type_str_lower not in type_mapping:
            return str

        return type_mapping[type_str_lower]

    def process(self) -> None:
        """Process the node by creating a Pydantic model from field definitions."""
        # Get the schema name
        schema_name: str = self.get_parameter_value("schema_name")
        if not schema_name:
            schema_name = "DynamicSchema"

        # Get the list of field definitions
        schema_fields = self.get_parameter_value("schema_fields")

        if not schema_fields:
            self.parameter_output_values["schema"] = None
            return

        # Ensure schema_fields is a list
        if not isinstance(schema_fields, list):
            schema_fields = [schema_fields]

        # Build the field definitions dictionary for the Pydantic model
        field_definitions: dict[str, Any] = {}

        for field_def in schema_fields:
            if not isinstance(field_def, dict):
                continue

            # Get field properties
            field_name = field_def.get("name", "")
            if field_name in field_definitions:
                # throw error if duplicate field names
                raise ValueError(f"Duplicate field name in schema fields: {field_name}")

            if not field_name:
                continue

            field_name_str = str(field_name).strip()
            if not field_name_str:
                raise ValueError("Field name cannot be empty")

            # Get type for this field
            type_value = field_def.get("type", "str")
            list_type_value = field_def.get("list_type", "str")

            # Check if type is a nested schema (dict with "properties" key)
            if isinstance(type_value, dict) and "properties" in type_value:
                # This is a nested schema - create a Pydantic model for it
                from griptape_nodes_library.utils.schema_utils import create_pydantic_model_from_schema

                field_type = create_pydantic_model_from_schema(type_value)
            elif type_value == "list" and list_type_value:
                # This is a typed list - handle the list item type
                if isinstance(list_type_value, dict) and "properties" in list_type_value:
                    # List of nested schemas
                    from griptape_nodes_library.utils.schema_utils import create_pydantic_model_from_schema

                    item_type = create_pydantic_model_from_schema(list_type_value)
                    field_type = list[item_type]
                else:
                    # List of simple types
                    item_type = get_type({"type": list_type_value})
                    field_type = list[item_type]
            else:
                # Simple type - use get_type
                field_type = get_type({"type": type_value})

            # Get description for this field
            description = field_def.get("description", "")

            # Create field with type and description using Pydantic's Field
            if description and str(description).strip():
                field_definitions[field_name_str] = (field_type, Field(description=str(description)))
            else:
                field_definitions[field_name_str] = (field_type, ...)

        if not field_definitions:
            self.parameter_output_values["schema"] = None
            return

        # Create the dynamic Pydantic model with the specified name
        schema_model = create_model(schema_name, **field_definitions)

        self.parameter_output_values["schema"] = schema_model.model_json_schema()
