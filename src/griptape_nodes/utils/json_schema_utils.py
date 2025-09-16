"""Utility functions for JSON schema to Pydantic model conversion.

This module provides functionality to dynamically create Pydantic models from JSON schemas,
enabling runtime model generation for configuration settings and library definitions.
The implementation is based on the Stack Overflow solution for dynamic Pydantic model creation.
"""

from typing import Any


def extract_custom_fields_from_schema(schema: dict, base_fields: set[str]) -> list[dict]:
    """Extract custom field information from the schema for frontend organization.

    This function processes a JSON schema to identify custom fields (not in base fields)
    and extract their metadata for frontend UI organization.

    Args:
        schema: Complete JSON schema containing properties and $defs
        base_fields: Set of field names that belong to base fields (not custom fields)

    Returns:
        List of dictionaries containing custom field metadata with keys:
        - key: The field key name
        - title: Human-readable title
        - category: Category for UI organization
        - settings: The actual field schema

    Example:
        base_fields = {"log_level", "workspace_directory"}
        custom_fields = extract_custom_fields_from_schema(schema, base_fields)
        # Returns: [{"key": "flow_production_tracking", "title": "Flow Production Tracking", ...}]
    """
    custom_fields = []
    defs = schema.get("$defs", {})

    for key, field_schema in schema.get("properties", {}).items():
        # Check if this is a custom field (not in base fields)
        if key not in base_fields:
            # Get the full schema information for each setting
            settings_schema = {}
            if "$ref" in field_schema:
                # Extract the definition name from the $ref
                ref_path = field_schema["$ref"]
                if ref_path.startswith("#/$defs/"):
                    def_name = ref_path[8:]  # Remove "#/$defs/" prefix
                    if def_name in defs:
                        def_schema = defs[def_name]
                        # Get the full properties schema for each setting
                        properties = def_schema.get("properties", {})
                        settings_schema = dict(properties.items())

            custom_fields.append(
                {
                    "key": key,
                    "title": key.replace("_", " ").title(),
                    "category": f"{key.replace('_', ' ').title()} Library",
                    "settings": settings_schema,
                }
            )

    return custom_fields


def extract_enum_from_json(json_data: dict[str, Any], category_key: str, category_value: str) -> dict[str, list] | None:
    """Extract enum information from JSON data for a specific category.

    Args:
        json_data: The JSON data to search in.
        category_key: The key to match for the category (e.g., "category").
        category_value: The value to match for the category (e.g., "auth").

    Returns:
        A dictionary mapping field names to their enum values, or None if not found.
    """
    if "settings" in json_data:
        for setting in json_data["settings"]:
            if setting.get(category_key) == category_value:
                schema = setting.get("schema", {})
                return {
                    field_name: field_schema["enum"]
                    for field_name, field_schema in schema.items()
                    if "enum" in field_schema
                }
    return None


def get_enum_info_from_json_data(
    json_data_list: list[dict[str, Any]], category_key: str, category_value: str
) -> dict[str, list]:
    """Get enum information for a specific category from multiple JSON data structures.

    Args:
        json_data_list: List of JSON data structures to search in.
        category_key: The key to match for the category.
        category_value: The value to match for the category.

    Returns:
        A dictionary mapping field names to their enum values.
    """
    for json_data in json_data_list:
        enum_info = extract_enum_from_json(json_data, category_key, category_value)
        if enum_info:
            return enum_info
    return {}


def infer_field_type(value: Any, enum_info: dict[str, list] | None = None, field_name: str = "") -> Any:
    """Infer the appropriate Python type for a field based on its value and enum info.

    Args:
        value: The default value for the field.
        enum_info: Dictionary mapping field names to their enum values.
        field_name: The name of the field (used to check for enum info).

    Returns:
        The appropriate Python type for the field.
    """
    if enum_info and field_name in enum_info:
        # Use Literal for enum fields - this will generate proper enum in schema
        from typing import Literal

        enum_values = enum_info[field_name]
        return Literal[tuple(enum_values)]
    if isinstance(value, bool):
        return bool
    if isinstance(value, int):
        return int
    if isinstance(value, float):
        return float
    return str
