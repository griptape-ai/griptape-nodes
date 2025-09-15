"""JSON Schema to Pydantic model conversion utilities.

This module provides utilities for converting JSON schemas to Pydantic models,
supporting enums, nested objects, arrays, and nullable types.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, create_model


def json_schema_to_pydantic_model(schema: dict[str, Any]) -> type[BaseModel]:
    """Convert JSON schema to Pydantic model with support for enums, nested objects, arrays, and nullable types.

    Args:
        schema: JSON schema dictionary with 'type', 'properties', 'required', and 'title' keys

    Returns:
        Pydantic model class generated from the schema

    Example:
        >>> schema = {
        ...     "type": "object",
        ...     "properties": {
        ...         "name": {"type": "string", "title": "Name"},
        ...         "age": {"type": "integer", "title": "Age"},
        ...         "status": {"type": "string", "enum": ["active", "inactive"], "title": "Status"}
        ...     },
        ...     "required": ["name"],
        ...     "title": "UserModel"
        ... }
        >>> UserModel = json_schema_to_pydantic_model(schema)
        >>> user = UserModel(name="John", age=30, status="active")
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
        """Recursively processes a field and returns its type and Field instance."""
        field_type = _determine_field_type(field_props, type_mapping)
        field_type = _handle_nullable_type(field_type, field_props)

        default_value = _get_default_value(field_name, field_props, required_fields)
        description = field_props.get("title", "")

        return (field_type, Field(default_value, description=description))

    # Process all fields
    for field_name, field_props in properties.items():
        model_fields[field_name] = process_field(field_name, field_props)

    return create_model(schema.get("title", "DynamicModel"), **model_fields)


def _determine_field_type(field_props: dict[str, Any], type_mapping: dict[str, type]) -> Any:
    """Determine the appropriate Python type for a JSON schema field, handling enums, objects, and arrays."""
    json_type = field_props.get("type", "string")
    enum_values = field_props.get("enum")

    # Handle Enums - use Literal types to avoid serialization warnings
    # Problem: Using Enum() classes causes Pydantic serialization warnings during schema generation
    # Solution: Use Literal[tuple(enum_values)] which serializes cleanly without warnings
    # The tuple() is required because Literal expects individual arguments, not a list
    if enum_values:
        return Literal[tuple(enum_values)]

    # Handle Nested Objects
    if json_type == "object" and "properties" in field_props:
        return json_schema_to_pydantic_model(field_props)

    # Handle Arrays
    if json_type == "array":
        return _handle_array_type(field_props, type_mapping)

    # Handle primitive types
    return type_mapping.get(json_type, str)


def _handle_array_type(field_props: dict[str, Any], type_mapping: dict[str, type]) -> Any:
    """Determine the type for array fields, supporting arrays of primitives, enums, and nested objects."""
    if "items" not in field_props:
        return list[str]

    item_props = field_props["items"]

    # Handle Arrays with Nested Objects
    if item_props.get("type") == "object":
        nested_model_type = json_schema_to_pydantic_model(item_props)
        return list[nested_model_type]

    # Handle Arrays with Enums - use Literal types to avoid serialization warnings
    # Same issue as above: Enum() classes cause warnings, Literal[tuple()] works cleanly
    if "enum" in item_props:
        enum_values = item_props["enum"]
        return list[Literal[tuple(enum_values)]]

    # Handle Arrays with primitive types
    primitive_type = type_mapping.get(item_props.get("type", "string"), str)
    return list[primitive_type]


def _handle_nullable_type(field_type: Any, field_props: dict[str, Any]) -> Any:
    """Convert field type to nullable (Optional) type if specified in schema."""
    nullable = field_props.get("nullable", False)
    if nullable:
        return field_type | None
    return field_type


def _get_default_value(field_name: str, field_props: dict[str, Any], required_fields: list[str]) -> Any:
    """Get the appropriate default value for a field based on whether it's required."""
    if field_name not in required_fields:
        default_value = field_props.get("default")
        # For enum fields, ensure we return the string value, not an enum instance
        if "enum" in field_props and default_value is not None:
            return str(default_value)
        return default_value
    return field_props.get("default", ...)


def infer_type_from_value(value: Any) -> str:
    """Infer JSON schema type from Python value.

    Args:
        value: Python value to infer type from

    Returns:
        JSON schema type string ('string', 'integer', 'number', 'boolean', 'array', 'object')

    Example:
        >>> infer_type_from_value(42)
        'integer'
        >>> infer_type_from_value("hello")
        'string'
        >>> infer_type_from_value([1, 2, 3])
        'array'
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"
