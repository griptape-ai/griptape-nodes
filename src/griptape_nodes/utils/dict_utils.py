from typing import Any


def to_dict(input_value: Any) -> dict:
    """Convert various input types to a dictionary."""
    result = {}  # Default return value

    try:
        if input_value is None:
            pass  # Keep empty dict
        elif isinstance(input_value, dict):
            result = input_value
        elif isinstance(input_value, str) and input_value.strip():
            result = _convert_string_to_dict(input_value)
        elif isinstance(input_value, (list, tuple)):
            result = _convert_sequence_to_dict(input_value)
        elif hasattr(input_value, "__dict__"):
            result = {k: v for k, v in input_value.__dict__.items() if not k.startswith("_")}
        else:
            # Simple values fallback
            result = {"value": input_value}

    except Exception:
        result = {}  # Reset to empty dict on error

    return result


def _convert_string_to_dict(input_str: str) -> dict:
    """Convert a string to a dictionary using various parsing strategies."""
    # Import modules at the function start to avoid unbound errors
    import ast
    import json

    # Clean the input string
    input_str = input_str.strip()

    # Check if it looks like a dictionary (starts with { and ends with })
    if input_str.startswith("{") and input_str.endswith("}"):
        # Try Python literal evaluation first (handles single quotes)
        try:
            parsed = ast.literal_eval(input_str)
            if isinstance(parsed, dict):
                return parsed
        except (SyntaxError, ValueError):
            pass

        # Try JSON parsing as fallback (handles double quotes)
        try:
            parsed = json.loads(input_str)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Try JSON parsing for non-dict-looking strings (arrays, etc.)
    try:
        parsed = json.loads(input_str)
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}  # noqa: TRY300
    except json.JSONDecodeError:
        pass

    # Process for key-value patterns
    if ":" in input_str or "=" in input_str:
        return _process_key_value_string(input_str)

    # Default for plain strings
    return {"value": input_str}


def _process_key_value_string(input_str: str) -> dict:
    """Process string with key:value or key=value patterns."""
    result = {}

    # Check for multiple lines
    if "\n" in input_str:
        lines = input_str.split("\n")
        for original_line in lines:
            line_stripped = original_line.strip()
            if not line_stripped:
                continue

            if ":" in line_stripped:
                key, value = line_stripped.split(":", 1)
                result[key.strip()] = value.strip()
            elif "=" in line_stripped:
                key, value = line_stripped.split("=", 1)
                result[key.strip()] = value.strip()
    # Single line
    elif ":" in input_str:
        key, value = input_str.split(":", 1)
        result[key.strip()] = value.strip()
    elif "=" in input_str:
        key, value = input_str.split("=", 1)
        result[key.strip()] = value.strip()

    return result


def _convert_sequence_to_dict(sequence: list | tuple) -> dict:
    """Convert a list or tuple to dictionary."""
    result = {}

    min_kv_length = 2  # Minimum length for key-value pairs
    for i, item in enumerate(sequence):
        if isinstance(item, tuple) and len(item) >= min_kv_length:
            key, *values = item  # Unpack first element as key, rest as values
            if hasattr(key, "__hash__") and key is not None:
                if len(values) == 1:
                    # If there's only one value, don't keep it as a list
                    result[key] = values[0]
                else:
                    # Multiple values, store as a list
                    result[key] = values
            else:
                result[f"item{i + 1}"] = item
        else:
            result[f"item{i + 1}"] = item

    return result


def merge_dicts(dct: dict | None, merge_dct: dict | None, *, add_keys: bool = True) -> dict:
    """Recursive dict merge.

    Inspired by :meth:``dict.update()``, instead of
    updating only top-level keys, merge_dicts recurses down into dicts nested
    to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
    ``dct``.

    This version will return a copy of the dictionary and leave the original
    arguments untouched.

    The optional argument ``add_keys``, determines whether keys which are
    present in ``merge_dict`` but not ``dct`` should be included in the
    new dict.

    Args:
        dct: onto which the merge is executed
        merge_dct: dct merged into dct
        add_keys: whether to add new keys

    Returns:
        dict: updated dict
    """
    dct = {} if dct is None else dct
    merge_dct = {} if merge_dct is None else merge_dct

    dct = dct.copy()

    if not add_keys:
        merge_dct = {k: merge_dct[k] for k in set(dct).intersection(set(merge_dct))}

    for key in merge_dct:
        if key in dct and isinstance(dct[key], dict):
            dct[key] = merge_dicts(dct[key], merge_dct[key], add_keys=add_keys)
        else:
            dct[key] = merge_dct[key]

    return dct


def set_dot_value(d: dict[str, Any], dot_path: str, value: Any) -> dict:
    """Sets a value on a nested dictionary using a dot-delimited key.

    E.g. set_dot_value({}, "my.key.value", 5)
    results in {'my': {'key': {'value': 5}}}

    Args:
        d: The dictionary to modify.
        dot_path: The dot-delimited key path.
        value: The value to set.

    Returns:
        The modified dictionary.
    """
    keys = dot_path.split(".")
    current = d
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value

    return d


def get_dot_value(d: dict[str, Any], dot_path: str, default: Any | None = None) -> Any:
    """Retrieves a value from a nested dictionary using a dot-delimited key.

    Returns `default` if the path does not exist or if an intermediate
    path element is not a dictionary.

    Example:
        d = {'my': {'key': {'value': 5}}}
        val = get_dot_value(d, "my.key.value", default=None)
        assert val == 5

    Args:
        d: The dictionary to search.
        dot_path: The dot-delimited key path.
        default: The default value to return if the path does not exist. Defaults to None.

    Returns:
        The value at the specified path, or `default` if not
    """
    keys = dot_path.split(".")
    current = d
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current
