# **ExtractionToolNode Class Documentation**

### Overview

The `ExtractionToolNode` class is a custom node in the Griptape framework that utilizes the `ExtractionTool` to extract data from various sources. This node provides a flexible way to process and output data using different extraction engines.

### Attributes

- **`prompt_driver`**: An optional string parameter specifying the prompt driver.
- **`extraction_type`**: An optional string parameter indicating the type of extraction (csv or json).
- **`column_names_string`**: An optional string parameter containing column names in a comma-separated format.
- **`template_schema`**: An optional string parameter providing a template schema for JSON extraction.

### Methods

#### `process()`

This method is responsible for processing the node's inputs and producing outputs. It:

1. Retrieves the values of the input parameters (`prompt_driver`, `extraction_type`, `column_names_string`, and `template_schema`) from the `parameter_values` dictionary.
1. Sets a default prompt driver if none is provided.
1. Creates an appropriate extraction engine based on the specified `extraction_type`.
1. Creates an instance of the `ExtractionTool` using the extracted parameters, including the chosen extraction engine and a rule for raw output.
1. Sets the output as the created tool.

#### `validate_node()`

This method validates the node's inputs to ensure they are valid before processing. It:

1. Checks if the prompt driver is provided; if so, it returns an empty list of exceptions.
1. Retrieves the API key from the environment variable specified in the Griptape configuration.
1. If the API key is not defined, it adds a `KeyError` exception to the list and returns it.

### Example Usage

```python
# Create an ExtractionToolNode instance
node = ExtractionToolNode()

# Set input parameters
node.parameter_values["prompt_driver"] = GriptapeCloudPromptDriver(model="gpt-4o")
node.parameter_values["extraction_type"] = "json"
node.parameter_values["column_names"] = "name,age,email"
node.parameter_values["template_schema"] = '{"name": "string", "age": "integer"}'

# Run the node's process method
node.process()
```

### Output

The `tool` attribute of the `parameter_output_values` dictionary will contain an instance of the `ExtractionTool` with the specified parameters.

### Supported Extraction Engines

- **CsvExtractionEngine**: Extracts data from CSV files using a prompt driver.
- **JsonExtractionEngine**: Extracts data from JSON files using a template schema and a prompt driver.

### Rules

The node supports adding rules to customize its behavior. In this example, the `Raw output please` rule is added for raw output.
