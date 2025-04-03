# Base Tool Node

## What is it?

The `BaseToolNode` is a custom node in Griptape that provides a generic implementation for initializing Griptape tools with configurable parameters.

## When would I use it?

Use this node when you want to:

- Create a new tool with customizable parameters
- Initialize a tool with specific settings (e.g., off-prompt mode)
- Integrate tools from various sources in your Griptape workflow

## How to use it

### Basic Setup

1. Add the `BaseToolNode` to your workspace
1. Connect it to other nodes that provide necessary input parameters (e.g., tool configuration)
1. Run the flow to see the created tool

### Fields

- **off_prompt**: A boolean indicating whether the tool should operate in off-prompt mode.

  - Input type: Boolean
  - Type: Boolean
  - Output type: Boolean
  - Default value: False
  - Tooltip:

- **tool**: The created tool, represented as a dictionary.

  - Input type: BaseTool
  - Type: BaseTool
  - Output type: BaseTool
  - Default value: None
  - Tooltip:

## Subclasses

### Calculator Tool Node

The `CalculatorToolNode` is a subclass of `BaseToolNode` that creates a calculator tool with customizable parameters.

#### Example Usage

```python
calculator_tool_node = CalculatorToolNode("Calculator Tool")
calculator_tool_node.add_parameter(
    Parameter(
        name="expression",
        input_types=["str"],
        type="str",
        output_type="str",
        default_value="1+2*3",
        tooltip="Expression to calculate",
    )
)
```

#### Process Method

```python
def process(self) -> None:
    off_prompt = self.parameter_values.get("off_prompt", False)

    # Create the tool
    tool = CalculatorTool(off_prompt=off_prompt)

    # Set the output
    self.parameter_output_values["tool"] = tool
```

### DateTime Tool Node

The `DateTimeToolNode` is a subclass of `BaseToolNode` that creates a datetime tool with customizable parameters.

#### Example Usage

```python
datetime_tool_node = DateTimeToolNode("Date and Time Tool")
datetime_tool_node.add_parameter(
    Parameter(
        name="format",
        input_types=["str"],
        type="str",
        output_type="str",
        default_value="%Y-%m-%d %H:%M:%S",
        tooltip="Format for datetime output",
    )
)
```

#### Process Method

```python
def process(self) -> None:
    off_prompt = self.parameter_values.get("off_prompt", False)

    # Create the tool
    tool = DateTimeTool(off_prompt=off_prompt)

    # Set the output
    self.parameter_output_values["tool"] = tool
```

### Web Search Tool Node

The `WebSearchToolNode` is a subclass of `BaseToolNode` that creates a web search tool with customizable parameters.

#### Example Usage

```python
web_search_tool_node = WebSearchToolNode("Web Search Tool")
web_search_tool_node.add_parameter(
    Parameter(
        name="query",
        input_types=["str"],
        type="str",
        output_type="str",
        default_value="Python programming language",
        tooltip="Query for web search",
    )
)
```

#### Process Method

```python
def process(self) -> None:
    off_prompt = self.parameter_values.get("off_prompt", False)
    driver = self.parameter_values.get("driver", None)
    if not driver:
        driver = DuckDuckGoWebSearchDriver()

    # Create the tool
    tool = WebSearchTool(off_prompt=off_prompt, web_search_driver=driver)

    # Set the output
    self.parameter_output_values["tool"] = tool
```

## Advantages

- Provides a generic implementation for initializing Griptape tools with customizable parameters.
- Allows for easy integration of tools from various sources in your Griptape workflow.

## Disadvantages

- May require additional configuration or setup depending on the specific use case.
