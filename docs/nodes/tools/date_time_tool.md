# **DateTimeToolNode Class Documentation**

### Overview

The `DateTimeToolNode` class is a custom node in the Griptape framework that utilizes the `DateTimeTool` to format and manipulate dates and times. This node provides a flexible way to process and output date and time data.

### Attributes

- **`off_prompt`**: An optional boolean parameter indicating whether to prompt for input or not (default: True).

### Methods

#### `process()`

This method is responsible for processing the node's inputs and producing outputs. It:

1. Retrieves the value of the `off_prompt` parameter from the `parameter_values` dictionary.
1. Creates an instance of the `DateTimeTool` using the extracted `off_prompt` value.
1. Sets the output as the created tool.

### Example Usage

```python
# Create a DateTimeToolNode instance
node = DateTimeToolNode()

# Set input parameters
node.parameter_values["off_prompt"] = False

# Run the node's process method
node.process()
```

### Output

The `tool` attribute of the `parameter_output_values` dictionary will contain an instance of the `DateTimeTool` with the specified `off_prompt` value.

### Supported Tools

- **DateTimeTool**: Formats and manipulates dates and times, optionally prompting for input.

### Rules

The node supports adding rules to customize its behavior. In this example, no additional rules are added.

### Configuration Options

| Option | Description |
| --- | --- |
| `off_prompt` | A boolean indicating whether to prompt for input or not (default: True). |

### Notes

- The `DateTimeTool` is a built-in tool in the Griptape framework that provides functionality for formatting and manipulating dates and times.
- By default, the `DateTimeTool` will prompt for input if `off_prompt` is set to False.
