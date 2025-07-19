# Display JSON

Display JSON data with automatic repair and formatting.

## Description

The Display JSON node takes JSON data and formats it for display. It uses `json-repair` to handle malformed JSON strings and provides a clean, readable output for viewing and debugging JSON data in your workflows.

## Parameters

### Input Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `json` | json, str, dict | The JSON data to display | `{}` |

### Output Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `json` | json | The formatted JSON data |

## Features

- **Automatic JSON Repair**: Handles malformed JSON strings using `json-repair`
- **Multiple Input Types**: Accepts dictionaries, strings, and other data types
- **Error Handling**: Graceful fallbacks when parsing fails
- **Display Optimization**: Formats JSON for easy reading and debugging
- **Real-time Processing**: Updates automatically when input changes

## Examples

### Basic JSON Display

```python
# Input: {"name": "John", "age": 30, "active": true}
# Output: {"name": "John", "age": 30, "active": true}
```

### Malformed JSON Repair and Display

```python
# Input: '{"name": "John", age: 30, "city": "New York"}'  # Missing quotes around age
# Output: {"name": "John", "age": 30, "city": "New York"}  # Repaired and formatted
```

### Complex JSON Structure

```python
# Input: {"user": {"name": "Alice", "profile": {"email": "alice@example.com", "preferences": {"theme": "dark"}}}}
# Output: {"user": {"name": "Alice", "profile": {"email": "alice@example.com", "preferences": {"theme": "dark"}}}}
```

### String to JSON Conversion and Display

```python
# Input: '{"items": [{"title": "Book", "price": 25}, {"title": "Magazine", "price": 10}]}'
# Output: {"items": [{"title": "Book", "price": 25}, {"title": "Magazine", "price": 10}]}
```

## Use Cases

- **Debugging**: View and inspect JSON data during workflow development
- **Data Validation**: Verify JSON structure and content
- **API Response Inspection**: Examine responses from external APIs
- **Configuration Review**: Check JSON configuration files
- **Data Flow Monitoring**: Monitor JSON data as it moves through your workflow

## Related Nodes

- [JSON Input](json_input.md) - Create JSON data from inputs
- [JSON Extract Value](json_extract_value.md) - Extract values from JSON
- [JSON Replace](json_replace.md) - Replace values in JSON
- [To JSON](to_json.md) - Convert other data types to JSON 