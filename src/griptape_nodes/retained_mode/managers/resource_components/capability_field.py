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
            # Basic type checking
            if schema_field.type_hint is list and not isinstance(value, list):
                errors.append(f"Field '{field_name}' should be a list, got {type(value).__name__}")
            elif schema_field.type_hint is bool and not isinstance(value, bool):
                errors.append(f"Field '{field_name}' should be a boolean, got {type(value).__name__}")
            elif schema_field.type_hint in (int, float) and not isinstance(value, (int, float)):
                errors.append(f"Field '{field_name}' should be numeric, got {type(value).__name__}")
            elif schema_field.type_hint is str and not isinstance(value, str):
                errors.append(f"Field '{field_name}' should be a string, got {type(value).__name__}")

    return errors
