**Web Scraper Tool Node Documentation**
=====================================

### Overview

The `WebScraperTool` class is a specialized node for creating Griptape tools that utilize web scraping functionality. This node provides a basic structure for initializing web scraper tools and can be extended to support various web scraping techniques.

### Class Definition

```python
class WebScraperTool(BaseTool):
    """A web scraper tool node for creating Griptape tools."""
```

### Initialization

The `__init__` method initializes a new instance of the `WebScraperTool` class. It takes two parameters:

*   **name (str)**: The name of the node.
*   **metadata (dict[Any, Any] | None)**: Optional metadata for the node.

```python
def __init__(
    self,
    name: str,
    metadata: dict[Any, Any] | None = None,
) -> None:
    """Initializes a new instance of the WebScraperTool class."""
    super().__init__(name, metadata)
```

### Processing

The `process` method is called when the node is executed. It retrieves the values of the defined parameters and creates a new instance of the `WebScraperTool` class based on those values.

```python
def process(self) -> None:
    """Processes the node and sets the output parameter."""
    off_prompt = self.parameter_values.get("off_prompt", False)
    tool = WebScraperTool(off_prompt=off_prompt)
    self.parameter_output_values["tool"] = tool
```

### Example Usage

To create a new instance of the `WebScraperTool` class, you can use the following code:

```python
node = WebScraperTool("My Web Scraper")
node.process()
print(node.parameter_output_values["tool"])
```

This will create a new node with the name "My Web Scraper" and process it to set the output parameter to the created web scraper tool instance.

### Notes

*   The `WebScraperTool` class is not defined in this code snippet. It is assumed to be a separate class that provides the actual web scraping functionality.
*   The `parameter_values` and `parameter_output_values` attributes are not defined in this code snippet. They are assumed to be dictionaries that store the input and output parameters of the node, respectively.

### Best Practices

*   When creating new nodes, ensure that you follow the same naming conventions and structure as existing nodes.
*   Use meaningful parameter names and descriptions to make your nodes more user-friendly.
*   Consider adding additional functionality or features to your nodes as needed.