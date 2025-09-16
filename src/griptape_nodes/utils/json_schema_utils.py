"""Utility functions for JSON schema to Pydantic model conversion.

This module provides functionality to dynamically create Pydantic models from JSON schemas,
enabling runtime model generation for configuration settings and library definitions.
The implementation is based on the Stack Overflow solution for dynamic Pydantic model creation.
"""

from typing import Any, Literal, Union

from pydantic import BaseModel, Field, create_model


def json_schema_to_pydantic_model(schema: dict[str, Any]) -> type[BaseModel]:
    """Convert a JSON schema to a Pydantic model.

    This function dynamically creates Pydantic models at runtime from JSON schema definitions.
    It handles various JSON schema types including objects, arrays, enums, and nested structures.
    The generated models can be used for validation and serialization of configuration data.

    Key features:
    - Supports all basic JSON schema types (string, integer, number, boolean, array, object)
    - Handles enum values using Literal types to avoid Pydantic serialization warnings
    - Recursively processes nested objects and arrays
    - Preserves field metadata like descriptions and default values
    - Handles nullable fields using Union types

    Based on the Stack Overflow solution:
    https://stackoverflow.com/questions/73841072/dynamically-generating-pydantic-model-from-a-schema-json-file/79431514#79431514

    Args:
        schema: JSON schema dictionary containing type definitions, properties, and constraints

    Returns:
        Pydantic model class that can be instantiated and used for validation

    Example:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "title": "Name"},
                "age": {"type": "integer", "default": 0}
            },
            "required": ["name"]
        }
        model_class = json_schema_to_pydantic_model(schema)
        instance = model_class(name="John", age=25)
    """
    type_mapping: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    properties = schema.get("properties", {})
    required_fields = schema.get("required", [])
    model_fields = {}

    def process_field(field_name: str, field_props: dict[str, Any]) -> tuple:
        """Recursively processes a field and returns its type and Field instance.

        This function handles the conversion of individual JSON schema field definitions
        into Pydantic field types and Field instances. It supports complex type handling
        including enums, nested objects, arrays, and nullable fields.

        Args:
            field_name: Name of the field being processed
            field_props: JSON schema properties for this field

        Returns:
            Tuple of (field_type, Field_instance) for use in create_model
        """
        json_type = field_props.get("type", "string")
        enum_values = field_props.get("enum")

        # Handle Enums: Convert to Literal types to avoid Pydantic serialization warnings
        # This approach is cleaner than using Enum classes and prevents warnings when
        # serializing enum values that don't match the enum class exactly
        if enum_values:
            # Create a Literal type with all enum values as a tuple
            # This ensures type safety while avoiding serialization issues
            field_type = Literal[tuple(enum_values)]

        # Handle Nested Objects: Recursively create Pydantic models for object types
        # This allows for complex nested structures in configuration schemas
        elif json_type == "object" and "properties" in field_props:
            field_type = json_schema_to_pydantic_model(field_props)

        # Handle Arrays: Support both simple arrays and arrays of complex objects
        # Arrays of objects get their own Pydantic model, simple types use basic Python types
        elif json_type == "array" and "items" in field_props:
            item_props = field_props["items"]
            if item_props.get("type") == "object":
                # Recursively create model for array items that are objects
                array_item_type = json_schema_to_pydantic_model(item_props)
            else:
                # Use basic Python types for simple array items
                array_item_type = type_mapping.get(item_props.get("type", "string"), Any)
            field_type = list[array_item_type]
        else:
            # Handle basic types using the type mapping
            field_type = type_mapping.get(json_type, Any)

        # Extract field metadata for Pydantic Field creation
        default_value = field_props.get("default", ...)  # Use ... for required fields
        nullable = field_props.get("nullable", False)
        description = field_props.get("title", "")

        # Handle nullable fields by creating Union types with None
        # This allows fields to accept either their primary type or None
        if nullable:
            # Use Union instead of | syntax because we're creating the union dynamically at runtime
            field_type = Union[field_type, None]  # noqa: UP007

        # Override default for non-required fields
        # Required fields keep ... as default, optional fields get None or their specified default
        if field_name not in required_fields:
            default_value = field_props.get("default")

        return (field_type, Field(default_value, description=description))

    for field_name, field_props in properties.items():
        model_fields[field_name] = process_field(field_name, field_props)

    return create_model(schema.get("title", "DynamicModel"), **model_fields)


def build_json_schema_from_settings(category: str, settings_data: dict, schema_info: dict) -> dict[str, Any]:
    """Build a JSON schema from library settings data and schema information.

    This function converts library configuration data into a proper JSON schema format
    that can be used to generate Pydantic models. It handles default values, type inference,
    and enum definitions from library definition files.

    The function is essential for the dynamic configuration system, allowing library
    settings to be properly typed and validated at runtime.

    Args:
        category: The category name for the settings (e.g., "flow_production_tracking")
        settings_data: The actual settings data dictionary with current values
        schema_info: Schema information from library definition file containing type hints

    Returns:
        JSON schema dictionary ready for Pydantic model generation

    Example:
        settings_data = {"auth": "API", "timeout": 30}
        schema_info = {"auth": {"type": "string", "enum": ["API", "user"]}}
        schema = build_json_schema_from_settings("flow_tracking", settings_data, schema_info)
    """
    # Initialize the JSON schema structure with basic object properties
    json_schema = {"type": "object", "properties": {}, "required": [], "title": f"{category.title()}Settings"}

    # Process each setting key-value pair to build the schema
    for key, value in settings_data.items():
        field_schema = schema_info.get(key, {})

        # Create property schema with type inference fallback
        # Use explicit type from schema_info if available, otherwise infer from value
        prop_schema = {
            "type": field_schema.get("type", infer_type_from_value(value)),
            "title": key.replace("_", " ").title(),  # Convert snake_case to Title Case
        }

        # Handle enum definitions from library schema
        # Enums are crucial for validation and UI dropdown generation
        if "enum" in field_schema:
            prop_schema["enum"] = field_schema["enum"]

        # Set default values with priority: schema_info > current value > None
        if "default" in field_schema:
            prop_schema["default"] = field_schema["default"]
        elif value is not None:
            prop_schema["default"] = value

        json_schema["properties"][key] = prop_schema

        # Mark fields as required if they have no default and current value is None
        # This ensures proper validation of mandatory configuration fields
        if "default" not in field_schema and value is None:
            json_schema["required"].append(key)

    return json_schema


def infer_type_from_value(value: Any) -> str:
    """Infer JSON schema type from Python value.

    This function provides type inference for configuration values when explicit
    type information is not available in the library schema. It maps Python
    runtime types to their corresponding JSON schema type strings.

    The type inference is essential for dynamic configuration systems where
    library definitions may not specify explicit types for all fields.

    Args:
        value: Python value to infer type from (can be any Python object)

    Returns:
        JSON schema type string ("string", "integer", "number", "boolean", "array", "object")

    Example:
        infer_type_from_value(42) -> "integer"
        infer_type_from_value("hello") -> "string"
        infer_type_from_value(True) -> "boolean"
        infer_type_from_value([1, 2, 3]) -> "array"
        infer_type_from_value({"key": "value"}) -> "object"
    """
    # Type mapping with priority order (bool must come before int)
    type_mapping = [
        (bool, "boolean"),
        (int, "integer"),
        (float, "number"),
        (str, "string"),
        (list, "array"),
        (dict, "object"),
    ]

    # Check each type in order and return the first match
    for python_type, json_type in type_mapping:
        if isinstance(value, python_type):
            return json_type

    # Default fallback to string for unknown types
    return "string"
