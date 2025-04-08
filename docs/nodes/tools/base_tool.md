# **Base Tool Node Documentation**

### Overview

The `BaseTool` class is a generic implementation for creating Griptape tools with configurable parameters. This node provides a basic structure for initializing tools and can be extended to support various tool types.

### Attributes

- **off_prompt (bool)**: Indicates whether the tool should operate in off-prompt mode.
- **tool (BaseTool)**: A dictionary representation of the created tool.

### Class Definition

```python
class BaseTool(DataNode):
    """Base tool node for creating Griptape tools."""
```

### Initialization

The `__init__` method initializes a new instance of the `BaseTool` class. It takes two parameters:

- **name (str)**: The name of the node.
- **metadata (dict | None)**: Optional metadata for the node.

```python
def __init__(self, name: str, metadata: dict | None = None) -> None:
    super().__init__(name, metadata)
```

### Parameters

The `BaseTool` class defines two parameters:

- **off_prompt (bool)**: A boolean parameter that determines whether the tool operates in off-prompt mode.
- **tool (BaseTool)**: A dictionary representation of the created tool.

```python
def add_parameter(self, parameter: Parameter) -> None:
    """Adds a new parameter to the node."""
```

### Processing

The `process` method is called when the node is executed. It retrieves the values of the defined parameters and creates a new instance of the `BaseTool` class based on those values.

```python
def process(self) -> None:
    """Processes the node and sets the output parameter."""
    off_prompt = self.parameter_values.get("off_prompt", False)
    tool = BaseTool(off_prompt=off_prompt)
    self.parameter_output_values["tool"] = tool
```

### Example Usage

To create a new instance of the `BaseTool` class, you can use the following code:

```python
node = BaseTool("My Tool")
node.process()
print(node.parameter_output_values["tool"])
```

This will create a new node with the name "My Tool" and process it to set the output parameter to the created tool instance.
