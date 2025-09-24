"""Capability field definition for resource schemas."""

from dataclasses import dataclass
from typing import Any


@dataclass
class CapabilityField:
    """Definition of a single capability field."""

    name: str
    type_hint: type
    description: str
    required: bool = True
    default: Any = None


def validate_capabilities(schema: list[CapabilityField], capabilities: dict[str, Any]) -> list[str]:
    """Validate capabilities against schema and return list of validation errors."""
    errors = []

    # Check required fields
    for field in schema:
        if field.required and field.name not in capabilities:
            errors.append(f"Required field '{field.name}' is missing")  # noqa: PERF401

    # Check field types (basic validation)
    for field_name, value in capabilities.items():
        schema_field = next((f for f in schema if f.name == field_name), None)
        if schema_field:
            # Handle numeric types (int/float are interchangeable)
            if schema_field.type_hint in (int, float):
                if not isinstance(value, (int, float)):
                    errors.append(f"Field '{field_name}' should be numeric, got {type(value).__name__}")
            # Standard type checking for all other types
            elif not isinstance(value, schema_field.type_hint):
                errors.append(
                    f"Field '{field_name}' should be a {schema_field.type_hint.__name__}, got {type(value).__name__}"
                )

    return errors
