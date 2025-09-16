"""Utility functions for JSON schema to Pydantic model conversion.

This module provides functionality to dynamically create Pydantic models from JSON schemas,
enabling runtime model generation for configuration settings and library definitions.
The implementation is based on the Stack Overflow solution for dynamic Pydantic model creation.
"""

from collections.abc import Callable
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


def build_json_schema_from_data(category: str, data: dict, schema_info: dict) -> dict[str, Any]:
    """Build a JSON schema from data and schema information.

    This function converts configuration data into a proper JSON schema format
    that can be used to generate Pydantic models. It handles default values, type inference,
    and enum definitions from schema information.

    Args:
        category: The category name for the data (e.g., "flow_production_tracking")
        data: The actual data dictionary with current values
        schema_info: Schema information containing type hints and constraints

    Returns:
        JSON schema dictionary ready for Pydantic model generation

    Example:
        data = {"auth": "API", "timeout": 30}
        schema_info = {"auth": {"type": "string", "enum": ["API", "user"]}}
        schema = build_json_schema_from_data("flow_tracking", data, schema_info)
    """
    # Initialize the JSON schema structure with basic object properties
    json_schema = {"type": "object", "properties": {}, "required": [], "title": f"{category.title()}Settings"}

    # Process each data key-value pair to build the schema
    for key, value in data.items():
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


def convert_schema_to_pydantic_type(field_schema: dict, default_value: Any) -> Any:  # noqa: ARG001
    """Convert a JSON schema field definition to a Pydantic type.

    This function maps JSON schema field types to their corresponding Python types,
    with special handling for enum fields to ensure clean JSON schema generation.

    Args:
        field_schema: JSON schema field definition containing type and constraints
        default_value: Default value for the field (used for type inference if needed)

    Returns:
        Python type that can be used in Pydantic model creation

    Example:
        field_schema = {"type": "string", "enum": ["A", "B"]}
        field_type = convert_schema_to_pydantic_type(field_schema, "A")
        # Returns: str (enum constraint handled via Field definition)
    """
    field_type = field_schema.get("type", "string")

    if "enum" in field_schema:
        # For enums, we'll use str type and handle the enum constraint in the Field definition
        # This ensures the JSON schema shows as a simple "enum" array instead of "anyOf"
        return str

    # Map field types to Python types
    type_mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return type_mapping.get(field_type, str)


def create_pydantic_model_from_schema(category: str, schema_info: dict, data: dict) -> type:
    """Create a Pydantic model from schema information with proper enum support.

    This function dynamically creates a Pydantic model from schema information,
    handling enum fields with proper JSON schema generation.

    Args:
        category: The category name for the model (e.g., "flow_production_tracking")
        schema_info: Schema information containing field definitions and types
        data: Current data with default values

    Returns:
        Pydantic model class that can be instantiated and used for validation

    Example:
        schema_info = {"auth": {"type": "string", "enum": ["API", "user"]}}
        data = {"auth": "API"}
        model_class = create_pydantic_model_from_schema("flow_tracking", schema_info, data)
        instance = model_class(auth="user")
    """
    field_definitions = {}

    for field_name, field_schema in schema_info.items():
        field_type = convert_schema_to_pydantic_type(field_schema, data.get(field_name))

        # Create Field with enum constraint if present
        if "enum" in field_schema:
            field_definitions[field_name] = (
                field_type,
                Field(default=data.get(field_name), json_schema_extra={"enum": field_schema["enum"]}),
            )
        else:
            field_definitions[field_name] = (field_type, Field(default=data.get(field_name)))

    return create_model(f"{category.title()}Settings", **field_definitions)


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


def extract_field_categories(model_fields: dict) -> dict[str, str]:
    """Extract category information from Pydantic model fields.

    This function processes Pydantic model fields to extract category information
    from their json_schema_extra metadata for frontend UI organization.

    Args:
        model_fields: Dictionary of model fields from a Pydantic model

    Returns:
        Dictionary mapping field names to their category strings

    Example:
        categories = extract_field_categories(Settings.model_fields)
        # Returns: {"synced_workflows_directory": "File System", ...}
    """
    categories = {}
    for field_name, field_info in model_fields.items():
        if (
            hasattr(field_info, "json_schema_extra")
            and field_info.json_schema_extra
            and isinstance(field_info.json_schema_extra, dict)
            and "category" in field_info.json_schema_extra
        ):
            categories[field_name] = field_info.json_schema_extra["category"]
    return categories


def extract_custom_field_schemas(
    config: dict,
    base_fields: set[str],
    schema_loader_func: Callable[[str], dict[str, Any] | None],
) -> dict[str, dict]:
    """Extract schema information for custom fields from configuration.

    This function processes a configuration to identify custom fields (not in base fields)
    and extracts their schema information using a provided loader function.

    Args:
        config: The configuration containing all fields
        base_fields: Set of field names that belong to base fields (not custom fields)
        schema_loader_func: Function to load schema for a specific field category

    Returns:
        Dictionary mapping field category names to their schema information

    Example:
        schemas = extract_custom_field_schemas(config, Settings.model_fields, load_func)
        # Returns: {"flow_production_tracking": {"auth": {"type": "string", "enum": ["API", "user"]}}}
    """
    custom_schemas = {}

    # Get custom fields that are already in config
    custom_fields = {key: value for key, value in config.items() if key not in base_fields and isinstance(value, dict)}

    # For each custom field, try to find its schema definition
    for category in custom_fields:
        schema_info = schema_loader_func(category)
        if schema_info:
            custom_schemas[category] = schema_info

    return custom_schemas


def get_diff(old_value: Any, new_value: Any) -> dict[Any, Any]:
    """Generate a diff between two values.

    This function compares two values and returns a dictionary representing
    the differences. It handles dictionaries, lists, and primitive values.

    Args:
        old_value: The original value to compare
        new_value: The new value to compare against

    Returns:
        Dictionary representing the differences between the values

    Example:
        diff = get_diff({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4})
        # Returns: {"b": (2, 3), "c": (None, 4)}
    """
    if isinstance(old_value, dict) and isinstance(new_value, dict):
        diff = {
            key: (old_value.get(key), new_value.get(key))
            for key in new_value
            if old_value.get(key) != new_value.get(key)
        }
    elif isinstance(old_value, list) and isinstance(new_value, list):
        diff = {
            str(i): (old, new) for i, (old, new) in enumerate(zip(old_value, new_value, strict=False)) if old != new
        }

        # Handle added or removed elements
        if len(old_value) > len(new_value):
            for i in range(len(new_value), len(old_value)):
                diff[str(i)] = (old_value[i], None)
        elif len(new_value) > len(old_value):
            for i in range(len(old_value), len(new_value)):
                diff[str(i)] = (None, new_value[i])
    else:
        diff = {"old": old_value, "new": new_value}
    return diff


def format_diff(diff: dict[Any, Any]) -> str:
    r"""Format a diff dictionary into a readable string.

    This function takes a diff dictionary and formats it into a human-readable
    string showing what was added, removed, or changed.

    Args:
        diff: Dictionary representing differences between values

    Returns:
        Formatted string showing the differences

    Example:
        diff = {"b": (2, 3), "c": (None, 4)}
        formatted = format_diff(diff)
        # Returns: "[b]:\n\tFROM: '2'\n\t  TO: '3'\n[c]: ADDED: '4'"
    """
    formatted_lines = []
    for key, (old, new) in diff.items():
        if old is None:
            formatted_lines.append(f"[{key}]: ADDED: '{new}'")
        elif new is None:
            formatted_lines.append(f"[{key}]: REMOVED: '{old}'")
        else:
            formatted_lines.append(f"[{key}]:\n\tFROM: '{old}'\n\t  TO: '{new}'")
    return "\n".join(formatted_lines)
