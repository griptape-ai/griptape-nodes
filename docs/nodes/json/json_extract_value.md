# JSON Extract Value

Extract values from JSON using [JMESPath](https://jmespath.org) expressions.

## Description

The JSON Extract Value node allows you to extract specific values from JSON data using JMESPath expressions. It supports nested object access, array indexing, and powerful wildcard operations, making it easy to navigate and extract data from complex JSON structures.

## Parameters

### Input Parameters

| Parameter     | Type            | Description                                                                                | Default |
| ------------ | --------------- | ------------------------------------------------------------------------------------------ | ------- |
| `json`       | json, str, dict | The JSON data to extract from                                                              | `{}`    |
| `path`       | str             | JMESPath expression to extract data (e.g., 'user.name', 'items[0].title', '[\*].assignee') | `""`    |
| `strip_quotes` | bool           | If enabled, removes outer quotes from simple string values (does not affect objects or arrays) | `false` |

### Output Parameters

| Parameter | Type | Description         |
| --------- | ---- | ------------------- |
| `output`  | json | The extracted value |

## Features

- **JMESPath Expressions**: Use powerful JMESPath syntax for flexible data extraction
- **Dot Notation Paths**: Use simple dot notation to navigate JSON structure
- **Array Indexing**: Access array elements using `[index]` syntax
- **Wildcard Operations**: Extract all values from arrays using `[*]` syntax
- **Quote Stripping**: Optionally remove outer quotes from simple string values for cleaner output
- **Real-time Updates**: Automatically updates when input changes
- **Safe Extraction**: Returns empty object `{}` if path doesn't exist
- **JSON Output**: Returns properly formatted JSON strings

## JMESPath Syntax

> **📚 Learn More**: For complete JMESPath syntax and advanced features, see the [JMESPath Documentation](https://jmespath.org/tutorial.html).

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

### Wildcard Operations

```python
# Extract all values from arrays
path = "items[*].title"      # Gets all titles from items array
path = "users[*].name"       # Gets all names from users array
path = "[*].assignee"        # Gets all assignees from root array
```

### Complex Paths

```python
# Combine object and array access
path = "orders[0].items[1].price"  # Gets price of second item in first order
path = "projects[*].tasks[*].assignee"  # Gets all assignees from all project tasks
```

## Examples

### Basic Object Extraction

```python
# Input JSON: {"user": {"name": "John", "age": 30}}
# Path: "user.name"
# Output (strip_quotes=false): "\"John\""  # With quotes
# Output (strip_quotes=true): "John"        # Without quotes
```

### Array Element Extraction

```python
# Input JSON: {"items": [{"title": "Book", "price": 25}, {"title": "Magazine", "price": 10}]}
# Path: "items[0].title"
# Output (strip_quotes=false): "\"Book\""  # With quotes
# Output (strip_quotes=true): "Book"        # Without quotes
```

### Nested Array Access

```python
# Input JSON: {"orders": [{"items": [{"name": "Product A"}, {"name": "Product B"}]}]}
# Path: "orders[0].items[1].name"
# Output (strip_quotes=false): "\"Product B\""  # With quotes
# Output (strip_quotes=true): "Product B"        # Without quotes
```

### Non-existent Path

```python
# Input JSON: {"user": {"name": "John"}}
# Path: "user.email"
# Output: "{}"  # Empty object for non-existent paths
```

### Quote Stripping Feature

The `strip_quotes` parameter allows you to remove outer quotes from simple string values, making the output cleaner for use in other nodes:

```python
# Input JSON: {"product": {"name": "Widget", "category": "Electronics"}}
# Path: "product.name"
# strip_quotes=false: Output is "\"Widget\""  # JSON string with quotes
# strip_quotes=true: Output is "Widget"        # Plain string without quotes
```

**Important Notes:**
- Quote stripping only affects simple string values (values that start and end with quotes)
- Complex objects and arrays are never affected, even when `strip_quotes=true`
- This is useful when you need plain string values for text processing or concatenation
- When `strip_quotes=false`, the output is always valid JSON (objects/arrays are unchanged)

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
