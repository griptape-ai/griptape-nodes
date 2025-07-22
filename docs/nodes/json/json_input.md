# JSON Input

Creates a JSON node from input data with automatic repair capabilities.

## Description

The JSON Input node takes various input types and converts them to proper JSON data. It uses `json-repair` to handle malformed JSON strings and provides robust conversion for different data types.

## Parameters

### Input Parameters

| Parameter | Type            | Description                       | Default |
| --------- | --------------- | --------------------------------- | ------- |
| `json`    | json, str, dict | The input data to convert to JSON | `{}`    |

### Output Parameters

| Parameter | Type | Description             |
| --------- | ---- | ----------------------- |
| `json`    | json | The processed JSON data |

## Features

- **Automatic JSON Repair**: Handles malformed JSON strings using `json-repair`
- **Multiple Input Types**: Accepts dictionaries, strings, and other data types
- **Error Handling**: Graceful fallbacks when parsing fails
- **Real-time Processing**: Updates automatically when input changes

## Examples

### Basic Usage

```python
# Input: {"name": "John", "age": 30}
# Output: {"name": "John", "age": 30}
```

### Malformed JSON Repair

```python
# Input: '{"name": "John", age: 30}'  # Missing quotes around age
# Output: {"name": "John", "age": 30}  # Repaired JSON
```

### String to JSON Conversion

```python
# Input: '{"user": {"name": "Alice", "active": true}}'
# Output: {"user": {"name": "Alice", "active": true}}
```

### Dictionary Input

```python
# Input: {"status": "active", "count": 5}
# Output: {"status": "active", "count": 5}  # Used as-is
```

## Use Cases

- **Data Validation**: Ensure input data is valid JSON
- **API Integration**: Process JSON responses from external APIs
- **Data Cleaning**: Repair malformed JSON data
- **Workflow Integration**: Convert various data types to JSON format

## Related Nodes

- [JSON Extract Value](json_extract_value.md) - Extract specific values from JSON
- [JSON Replace](json_replace.md) - Replace values in JSON
- [Display JSON](display_json.md) - Display and format JSON data
- [To JSON](../convert/to_json.md) - Convert other data types to JSON
