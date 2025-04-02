**Web Search Tool Node Documentation**
=====================================

### Overview

The `WebSearchToolNode` class is a specialized node for creating a Griptape web search tool. This node provides a basic structure for initializing tools based on provided drivers and can be extended to support various driver scenarios.

### Class Definition

```python
class WebSearchToolNode(BaseToolNode):
    """A node for creating a Griptape web search tool."""
```

### Initialization

The `WebSearchToolNode` class is initialized with the following parameters:

*   **driver (dict)**: A dictionary containing the driver configuration. If not provided, a default DuckDuckGoWebSearchDriver will be used.

    ```python
def __init__(self, **kwargs) -> None:
    """Initializes the Web Search Tool Node."""
    super().__init__(**kwargs)
    self.add_parameter(
        Parameter(
            name="driver",
            input_types=["dict"],
            type="dict",
            output_type="dict",
            default_value={},
            tooltip="",
        )
    )
```

### Processing

The `process` method is called when the node is executed. It retrieves the values of the defined parameters and creates a new instance of the `WebSearchTool` class based on those values.

```python
def process(self) -> None:
    """Processes the node and sets the output parameter."""
    off_prompt = self.parameter_values.get("off_prompt", False)
    driver_dict = self.parameter_values.get("driver", {})
    if driver_dict:
        # Create a web search driver from the provided dictionary
        driver = BaseWebSearchDriver.from_dict(driver_dict)  # pyright: ignore[reportAttributeAccessIssue] TODO(collin): Make Web Search Drivers serializable
    else:
        # Use a default DuckDuckGoWebSearchDriver if no driver is provided
        driver = DuckDuckGoWebSearchDriver()

    # Create the tool
    tool = WebSearchTool(off_prompt=off_prompt, web_search_driver=driver)

    # Set the output
    self.parameter_output_values["tool"] = tool
```

### Parameters

The `WebSearchToolNode` class accepts the following parameters:

*   **driver (dict)**: A dictionary containing the driver configuration. If not provided, a default DuckDuckGoWebSearchDriver will be used.

### Example Usage

To create a new instance of the `WebSearchToolNode` class, you can use the following code:

```python
node = WebSearchToolNode()
# node.parameter_values["driver"] = {"api_key": "1234567890", "language": "en"}
node.process()
print(node.parameter_output_values["tool"])
```

This will create a new node with no driver configuration and process it to set the output parameter to the created tool instance.

### Notes

*   The `BaseWebSearchDriver` class is not defined in this code snippet. It is assumed to be a separate class that provides the actual web search functionality.
*   The `DuckDuckGoWebSearchDriver` class is used as a default driver if no custom driver is provided.
*   The `parameter_values` and `parameter_output_values` attributes are not defined in this code snippet. They are assumed to be dictionaries that store the input and output parameters of the node, respectively.

### Best Practices

*   When creating new nodes, ensure that you follow the same naming conventions and structure as existing nodes.
*   Use meaningful parameter names and descriptions to make your nodes more user-friendly.
*   Consider adding additional functionality or features to your nodes as needed.