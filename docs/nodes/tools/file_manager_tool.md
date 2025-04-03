# File Manager Tool Node

## Overview

The `FileManagerToolNode` is a custom node in Griptape that provides a generic implementation for initializing Griptape file manager tools with customizable parameters.

## Subclassing BaseToolNode

#### What does it mean?

The `FileManagerToolNode` class is a subclass of `BaseToolNode`, inheriting its properties and behavior. This allows us to build upon the existing functionality of `BaseToolNode` while adding our own specific implementation for file manager tools.

#### Why would I use it?

Use this node when you want to:

- Create a new file manager tool with customizable parameters
- Initialize a file manager tool with specific settings (e.g., off-prompt mode)
- Integrate file manager tools from various sources in your Griptape workflow

## Class Definition

```python
class FileManagerToolNode(BaseToolNode):
    """
    A custom node for initializing Griptape file manager tools with customizable parameters.
    """
```

## Process Method

#### What does it do?

The `process` method is responsible for creating and setting the output of the file manager tool.

#### Example Usage

```python
file_manager_tool_node = FileManagerToolNode("File Manager Tool")
file_manager_tool_node.add_parameter(
    Parameter(
        name="off_prompt",
        input_types=["bool"],
        type="bool",
        output_type="bool",
        default_value=True,
        tooltip="",
    )
)
```

#### Code Snippet

```python
def process(self) -> None:
    """
    Creates and sets the output of the file manager tool.
    """
    off_prompt = self.parameter_values.get("off_prompt", True)

    # Create the tool
    tool = FileManagerTool(off_prompt=off_prompt)

    # Set the output
    self.parameter_output_values["tool"] = tool
```

#### Fields

- **off_prompt**: A boolean indicating whether the file manager tool should operate in off-prompt mode.
  - Input type: Boolean
  - Type: Boolean
  - Output type: Boolean
  - Default value: True
  - Tooltip:

## Advantages

- Provides a generic implementation for initializing Griptape file manager tools with customizable parameters.
- Allows for easy integration of file manager tools from various sources in your Griptape workflow.

## Disadvantages

- May require additional configuration or setup depending on the specific use case.

## Integration with Griptape Workflow

The `FileManagerToolNode` can be integrated into a Griptape workflow by adding it as a node and configuring its parameters. The output of the file manager tool can then be used in subsequent nodes or workflows.

```python
# Create a new file manager tool node
file_manager_tool_node = FileManagerToolNode("File Manager Tool")

# Add parameters to the node
file_manager_tool_node.add_parameter(
    Parameter(
        name="off_prompt",
        input_types=["bool"],
        type="bool",
        output_type="bool",
        default_value=True,
        tooltip="",
    )
)

# Create a new file manager tool and set its output
file_manager_tool = FileManagerTool(off_prompt=file_manager_tool_node.parameter_values["off_prompt"])
file_manager_tool_node.parameter_output_values["tool"] = file_manager_tool

# Use the output of the file manager tool in subsequent nodes or workflows
```

## Conclusion

The `FileManagerToolNode` provides a convenient way to initialize Griptape file manager tools with customizable parameters. By subclassing `BaseToolNode` and adding our own implementation for file manager tools, we can create a flexible and reusable node that can be integrated into various Griptape workflows.

### Best Practices

- Use the `FileManagerToolNode` when you need to integrate a file manager tool from an external source or library.
- Configure the `off_prompt` parameter according to your specific use case.
- Use the output of the file manager tool in subsequent nodes or workflows as needed.
