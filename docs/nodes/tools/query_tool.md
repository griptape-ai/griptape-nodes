**GeminiQueryTool Class Documentation**
=====================================

### Overview

The `GeminiQueryTool` class is a specialized query tool designed to work with Gemini models. It inherits from the `QueryTool` class and provides a natural language search functionality.

### Attributes

*   **`query` method**: This method takes in a dictionary of parameters, including a query string and content information. It processes the query using the Rag engine and returns a list of artifacts or an error artifact if no results are found.
*   **`params` attribute**: A dictionary containing the input parameters for the `query` method.

### Configuration

The `GeminiQueryTool` class has the following configuration options:

*   **`description`**: A brief description of the tool's purpose.
*   **`schema`**: A schema defining the expected structure of the input parameters. The schema includes two fields: `query` (a string) and `content` (an object with `memory_name` and `artifact_namespace` properties).

### Usage

To use the `GeminiQueryTool`, create an instance of the class and call the `query` method, passing in a dictionary of parameters. The tool will process the query using the Rag engine and return a list of artifacts or an error artifact.

# **QueryTool Class Documentation**

### Overview

The `QueryTool` class is a base class for generating query tools based on the provided prompt driver. It provides a way to create specialized query tools for Gemini models or standard query tools for other driver types.

### Attributes

*   **`process` method**: This method creates an instance of either the `GeminiQueryTool` or `QueryTool` class, depending on the type of prompt driver used.
*   **`prompt_driver` attribute**: The prompt driver object used to create the query tool.

### Configuration

The `QueryTool` class has the following configuration options:

*   **`description`**: A brief description of the tool's purpose.
*   **`schema`**: A schema defining the expected structure of the input parameters. The schema includes a field for the prompt driver object.

### Usage

To use the `QueryTool`, create an instance of the class and call the `process` method, passing in any required parameters. The tool will create an instance of either the `GeminiQueryTool` or `QueryTool` class, depending on the type of prompt driver used.

**Example Usage**
-----------------

```python
# Create a GeminiQueryTool instance
tool = GeminiQueryTool()

# Process a query using the Rag engine
outputs = tool.query({"values": {"query": "example query", "content": {"memory_name": "my_memory", "artifact_namespace": "my_namespace"}}})

# Create a QueryTool instance
node = QueryTool(prompt_driver=GooglePromptDriver())

# Process a query using the Rag engine
tool = node.process()
```

**API Documentation**
--------------------

### `GeminiQueryTool` Class

#### `query` method

*   **Parameters**: `params` (dict) - A dictionary of input parameters.
*   **Returns**: `ListArtifact | ErrorArtifact` - A list of artifacts or an error artifact if no results are found.

#### `params` attribute

*   **Type**: `dict`
*   **Description**: A dictionary containing the input parameters for the `query` method.

### `QueryTool` Class

#### `process` method

*   **Parameters**: None
*   **Returns**: `GeminiQueryTool | QueryTool` - An instance of either the `GeminiQueryTool` or `QueryTool` class.
*   **Description**: Creates an instance of either the `GeminiQueryTool` or `QueryTool` class, depending on the type of prompt driver used.