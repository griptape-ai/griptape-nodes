# Calculator Tool Node

## Overview

The `CalculatorTool` is a custom node in Griptape that provides a generic implementation for initializing Griptape tools with customizable parameters.

## Subclassing BaseTool

#### What does it mean?

The `CalculatorTool` class is a subclass of `BaseTool`, inheriting its properties and behavior. This allows us to build upon the existing functionality of `BaseTool` while adding our own specific implementation for calculator tools.

#### Why would I use it?

Use this node when you want to:

- Create a new calculator tool with customizable parameters
- Initialize a calculator tool with specific settings (e.g., off-prompt mode)
- Integrate calculator tools from various sources in your Griptape workflow


#### Parameters

**Inputs:**

- **off_prompt**: A boolean indicating whether the calculator tool should operate in off-prompt mode.


## Advantages

- Provides a generic implementation for initializing Griptape tools with customizable parameters.
- Allows for easy integration of calculator tools from various sources in your Griptape workflow.

## Disadvantages

- May require additional configuration or setup depending on the specific use case.

## Integration with Griptape Workflow

The `CalculatorTool` can be integrated into a Griptape workflow by adding it as a node and configuring its parameters. The output of the calculator tool can then be used in subsequent nodes or workflows.

```python
# Create a new calculator tool node
calculator_tool_node = CalculatorTool("Calculator Tool")

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

The `CalculatorTool` provides a convenient way to initialize Griptape tools with customizable parameters. By subclassing `BaseTool` and adding our own implementation for calculator tools, we can create a flexible and reusable node that can be integrated into various Griptape workflows.
