# Calculator Tool Node

## Overview

The `CalculatorToolNode` is a custom node in Griptape that provides a generic implementation for initializing Griptape tools with customizable parameters.

## Subclassing BaseTool

#### What does it mean?

The `CalculatorToolNode` class is a subclass of `BaseTool`, inheriting its properties and behavior. This allows us to build upon the existing functionality of `BaseTool` while adding our own specific implementation for calculator tools.

#### Why would I use it?

Use this node when you want to:

- Create a new calculator tool with customizable parameters
- Initialize a calculator tool with specific settings (e.g., off-prompt mode)
- Integrate calculator tools from various sources in your Griptape workflow

## Class Definition

```python
class CalculatorToolNode(BaseTool):
    """
    A custom node for initializing Griptape tools with customizable parameters.
    """
```

## Process Method

#### What does it do?

The `process` method is responsible for creating and setting the output of the calculator tool.

#### Example Usage

```python
calculator_tool_node = CalculatorToolNode("Calculator Tool")
calculator_tool_node.add_parameter(
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
    Creates and sets the output of the calculator tool.
    """
    off_prompt = self.parameter_values.get("off_prompt", True)

    # Create the tool
    tool = CalculatorTool(off_prompt=off_prompt)

    # Set the output
    self.parameter_output_values["tool"] = tool
```

#### Fields

- **off_prompt**: A boolean indicating whether the calculator tool should operate in off-prompt mode.
  - Input type: Boolean
  - Type: Boolean
  - Output type: Boolean
  - Default value: True
  - Tooltip:

## Advantages

- Provides a generic implementation for initializing Griptape tools with customizable parameters.
- Allows for easy integration of calculator tools from various sources in your Griptape workflow.

## Disadvantages

- May require additional configuration or setup depending on the specific use case.

## Integration with Griptape Workflow

The `CalculatorToolNode` can be integrated into a Griptape workflow by adding it as a node and configuring its parameters. The output of the calculator tool can then be used in subsequent nodes or workflows.

```python
# Create a new calculator tool node
calculator_tool_node = CalculatorToolNode("Calculator Tool")

# Add parameters to the node
calculator_tool_node.add_parameter(
    Parameter(
        name="off_prompt",
        input_types=["bool"],
        type="bool",
        output_type="bool",
        default_value=True,
        tooltip="",
    )
)

# Create a new calculator tool and set its output
calculator_tool = CalculatorTool(off_prompt=calculator_tool_node.parameter_values["off_prompt"])
calculator_tool_node.parameter_output_values["tool"] = calculator_tool

# Use the output of the calculator tool in subsequent nodes or workflows
```

## Conclusion

The `CalculatorToolNode` provides a convenient way to initialize Griptape tools with customizable parameters. By subclassing `BaseTool` and adding our own implementation for calculator tools, we can create a flexible and reusable node that can be integrated into various Griptape workflows.
