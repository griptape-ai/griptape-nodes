from typing import Any


def to_dict(input_value) -> dict:
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


def _convert_string_to_dict(input_str) -> dict:
    """Convert a string to a dictionary using various parsing strategies."""
    # Try JSON first
    import json

    try:
        parsed = json.loads(input_str)
        if isinstance(parsed, dict):
            result = parsed
        else:
            result = {"value": parsed}
    except json.JSONDecodeError:
        # Process for key-value patterns
        input_str = input_str.strip()
        if ":" in input_str or "=" in input_str:
            result = _process_key_value_string(input_str)
        else:
            # Default for plain strings
            result = {"value": input_str}

    return result


def _process_key_value_string(input_str) -> dict:
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


def _convert_sequence_to_dict(sequence) -> dict:
    """Convert a list or tuple to dictionary."""
    result = {}
    length_check = 2
    for i, item in enumerate(sequence):
        if isinstance(item, tuple) and len(item) == length_check:
            key, value = item
            if hasattr(key, "__hash__") and key is not None:
                result[key] = value
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
