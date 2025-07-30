# To JSON

Converts incoming value to JSON data using json-repair.

## Description

The To JSON node converts various data types to JSON format using `json-repair` for robust handling of malformed JSON strings. It provides intelligent conversion for different input types and includes automatic repair capabilities.

## Parameters

### Input Parameters

| Parameter | Type | Description                 | Default |
| --------- | ---- | --------------------------- | ------- |
| `from`    | any  | The data to convert to JSON | `{}`    |

### Output Parameters

| Parameter | Type | Description                |
| --------- | ---- | -------------------------- |
| `output`  | json | The converted data as JSON |

## Features

- **JSON Repair Integration**: Uses `json_repair.repair_json()` to handle malformed JSON strings
- **Multiple Input Type Support**: Handles different input types intelligently
- **Error Handling**: Graceful fallbacks when repair or parsing fails
- **Robust Conversion**: Can handle various input formats and convert them to proper JSON data

## Examples

### Dictionary to JSON

```python
# Input: {"name": "John", "age": 30, "active": True}
# Output: {"name": "John", "age": 30, "active": true}
```

### Malformed JSON String Repair

```python
# Input: '{"name": "John", age: 30, "city": "New York"}'  # Missing quotes around age
# Output: {"name": "John", "age": 30, "city": "New York"}  # Repaired JSON
```

### Regular JSON String

```python
# Input: '{"user": {"name": "Alice", "active": true}}'
# Output: {"user": {"name": "Alice", "active": true}}
```

### List to JSON

```python
# Input: [1, 2, 3, "four", {"nested": "value"}]
# Output: [1, 2, 3, "four", {"nested": "value"}]
```

### Other Data Types

```python
# Input: "simple string"
# Output: "simple string"

# Input: 42
# Output: 42

# Input: True
# Output: true
```

## Input Type Handling

### Dictionary Input

- **Behavior**: Uses as-is if already a dict
- **Example**: `{"key": "value"}` → `{"key": "value"}`

### String Input

- **Behavior**: Attempts to repair malformed JSON, falls back to regular JSON parsing
- **Example**: `'{"name": "John", age: 30}'` → `{"name": "John", "age": 30}`

### Other Types

- **Behavior**: Converts to string first, then attempts repair, with fallback to empty dict
- **Example**: `[1, 2, 3]` → `[1, 2, 3]`

## Use Cases

- **Data Standardization**: Convert various data formats to JSON
- **API Integration**: Prepare data for JSON-based APIs
- **Data Cleaning**: Repair and standardize malformed JSON data
- **Workflow Integration**: Convert different data types to JSON format for processing
- **Configuration Processing**: Handle configuration data in various formats

## Related Nodes

- [JSON Input](../json/json_input.md) - Create JSON data from inputs
- [JSON Extract Value](../json/json_extract_value.md) - Extract values from JSON
- [JSON Replace](../json/json_replace.md) - Replace values in JSON
- [Display JSON](../json/display_json.md) - Display and format JSON data
