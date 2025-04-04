# **VectorStoreToolNode Class Documentation**

### Overview

The `VectorStoreToolNode` class is a custom node in the Griptape framework that utilizes the `VectorStoreTool` to interact with a vector store. This node provides a flexible way to process and output data from a vector store.

### Attributes

- **`off_prompt`**: A boolean parameter indicating whether to prompt for input off.
- **`optional_query_params`**: An optional string parameter containing query parameters in JSON format.
- **`description`**: An optional string parameter providing a description of the tool.
- **`vector_store_driver`**: An optional object parameter specifying the vector store driver.

### Methods

#### `process()`

This method is responsible for processing the node's inputs and producing outputs. It:

1. Retrieves the values of the input parameters (`off_prompt`, `optional_query_params`, `description`, and `vector_store_driver`) from the `parameter_values` dictionary.
1. Creates a dictionary (`params`) containing these parameter values.
1. If `query_params` is provided, it converts the string to a dictionary using the `string_to_dict()` method.
1. If `description` is provided, it adds the description to the `params` dictionary.
1. If `vector_store_driver` is provided, it adds the driver to the `params` dictionary.
1. Creates an instance of the `VectorStoreTool` using the `params` dictionary and sets it as the output.

#### `string_to_dict(s)`

This method attempts to convert a string (`s`) into a dictionary in various formats:

1. **JSON format**: It tries to parse the string as JSON.
1. **Literal eval**: If parsing as JSON fails, it attempts to evaluate the string using Python's literal evaluation syntax.
1. **Key-value pair format**: If both previous methods fail, it splits the string into key-value pairs and creates a dictionary from them.

If any of these conversions fail, it logs an exception and returns an empty dictionary.

### Example Usage

```python
# Create a VectorStoreToolNode instance
node = VectorStoreToolNode()

# Set input parameters
node.parameter_values["off_prompt"] = True
node.parameter_values["optional_query_params"] = '{"key": "value"}'
node.parameter_values["description"] = "This is a description"
node.parameter_values["vector_store_driver"] = DummyVectorStoreDriver()

# Run the node's process method
node.process()
```

### Output

The `tool` attribute of the `parameter_output_values` dictionary will contain an instance of the `VectorStoreTool` with the specified parameters.
