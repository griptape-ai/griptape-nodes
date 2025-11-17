"""Type inference utilities for detecting value types, including string representations."""

import json
from typing import Any


def infer_type_from_value(value: Any) -> str:  # noqa: PLR0911
    """Infer the actual type of a value, handling string representations of numbers and JSON.

    If a value is a string, attempts to determine if it represents an int, float, bool,
    dict (JSON object), or list (JSON array). This is useful when values have been
    serialized (e.g., from JSON) and numeric/structured values are stored as strings.

    Args:
        value: The value to infer the type for

    Returns:
        The inferred type name as a string (e.g., 'int', 'float', 'str', 'dict', 'list', 'bool', etc.)

    Examples:
        >>> infer_type_from_value("123")
        'int'
        >>> infer_type_from_value("123.45")
        'float'
        >>> infer_type_from_value("true")
        'bool'
        >>> infer_type_from_value('{"key": "value"}')
        'dict'
        >>> infer_type_from_value("[1, 2, 3]")
        'list'
        >>> infer_type_from_value("hello")
        'str'
    """
    if value is None:
        return "NoneType"

    if not isinstance(value, str):
        return type(value).__name__

    # Try to parse as JSON first (handles dict, list, bool, null)
    try:
        parsed = json.loads(value)
        if parsed is None:
            return "NoneType"
        return type(parsed).__name__
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to parse as bool (case-insensitive)
    # Ensure value is a string before calling .lower()
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return "bool"

    # Try to parse as int first (more specific)
    try:
        int(value)
        if "." in value:
            float(value)
            return "float"
        return "int"  # noqa: TRY300
    except ValueError:
        pass

    # Try to parse as float
    try:
        float(value)
        return "float"  # noqa: TRY300
    except ValueError:
        pass

    # Final fallback: if it can't be parsed as anything else, it's a string
    return "str"
