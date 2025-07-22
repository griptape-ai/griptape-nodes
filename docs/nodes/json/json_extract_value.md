# JSON Extract Value

Extract a value from JSON using dot notation path.

## Description

The JSON Extract Value node allows you to extract specific values from JSON data using dot notation paths. It supports nested object access and array indexing, making it easy to navigate complex JSON structures.

## Parameters

### Input Parameters

| Parameter | Type            | Description                                                        | Default |
| --------- | --------------- | ------------------------------------------------------------------ | ------- |
| `json`    | json, str, dict | The JSON data to extract from                                      | `{}`    |
| `path`    | str             | Dot notation path to extract (e.g., 'user.name', 'items[0].title') | `""`    |

### Output Parameters

| Parameter | Type | Description         |
| --------- | ---- | ------------------- |
| `output`  | json | The extracted value |

## Features

- **Dot Notation Paths**: Use simple dot notation to navigate JSON structure
- **Array Indexing**: Access array elements using `[index]` syntax
- **Real-time Updates**: Automatically updates when input changes
- **Safe Extraction**: Returns empty object `{}` if path doesn't exist
- **String Output**: Converts extracted values to readable strings

## Path Syntax

### Basic Object Access

```python
# Access nested object properties
path = "user.name"           # Gets user's name
path = "user.profile.email"  # Gets nested email
```

### Array Indexing

```python
# Access array elements
path = "items[0]"            # Gets first item
path = "items[0].title"      # Gets title of first item
path = "users[2].name"       # Gets name of third user
```

### Complex Paths

```python
# Combine object and array access
path = "orders[0].items[1].price"  # Gets price of second item in first order
```

## Examples

### Basic Object Extraction

```python
# Input JSON: {"user": {"name": "John", "age": 30}}
# Path: "user.name"
# Output: "John"
```

### Array Element Extraction

```python
# Input JSON: {"items": [{"title": "Book", "price": 25}, {"title": "Magazine", "price": 10}]}
# Path: "items[0].title"
# Output: "Book"
```

### Nested Array Access

```python
# Input JSON: {"orders": [{"items": [{"name": "Product A"}, {"name": "Product B"}]}]}
# Path: "orders[0].items[1].name"
# Output: "Product B"
```

### Non-existent Path

```python
# Input JSON: {"user": {"name": "John"}}
# Path: "user.email"
# Output: "{}"  # Empty object for non-existent paths
```

## Use Cases

- **API Response Processing**: Extract specific fields from API responses
- **Data Filtering**: Get only the data you need from large JSON objects
- **Configuration Access**: Extract specific settings from configuration files
- **Data Transformation**: Prepare data for other nodes in your workflow

## Related Nodes

- [JSON Input](json_input.md) - Create JSON data from inputs
- [JSON Replace](json_replace.md) - Replace values in JSON
- [Display JSON](display_json.md) - Display and format JSON data
- [To JSON](../convert/to_json.md) - Convert other data types to JSON
