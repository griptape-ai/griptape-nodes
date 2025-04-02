# Prompt Summary Tool Node

## Overview

The `PromptSummaryToolNode` is a custom node in Griptape that provides a generic implementation for summarizing text using a prompt driver. This node creates and configures a `PromptSummaryTool` with an optional prompt driver.

## Subclassing BaseToolNode

#### What does it mean?
The `PromptSummaryToolNode` class is a subclass of `BaseToolNode`, inheriting its properties and behavior. This allows us to build upon the existing functionality of `BaseToolNode` while adding our own specific implementation for summarizing text.

#### Why would I use it?
Use this node when you want to:
- Summarize text using a prompt driver
- Create a configured PromptSummaryTool with an optional prompt driver
- Integrate the summary tool into your Griptape workflow

## Class Definition

```python
class PromptSummaryToolNode(BaseToolNode):
    """
    A custom node for summarizing text using a prompt driver.

    This class extends BaseToolNode to create a tool specifically for summarizing text.
    It configures a PromptSummaryEngine with an optional prompt driver and wraps it
    in a PromptSummaryTool.
    """

    def process(self) -> None:
        """
        Process method that creates and configures the PromptSummaryTool.

        This method:
        1. Gets the prompt driver from parameter_values (or uses default if none)
        2. Creates a PromptSummaryEngine with the prompt driver
        3. Creates a PromptSummaryTool with the engine
        4. Outputs the tool as a dictionary for later use
        """
```

## Process Method

#### What does it do?
The `process` method is responsible for creating and configuring the `PromptSummaryTool`.

#### Example Usage
```python
prompt_summary_tool_node = PromptSummaryToolNode("Text Summarizer")

# Add parameters to the node
prompt_summary_tool_node.add_parameter(
    Parameter(
        name="prompt_driver",
        input_types=["str"],
        type="string",
        output_type="string",
        default_value="default_prompt_driver",  # Use a default prompt driver if none provided
        tooltip="Prompt driver for summarization (e.g., 'default_prompt_driver', 'custom_prompt_driver')",
    )
)

# Create the node and process it
prompt_summary_tool_node.process()
```

#### Code Snippet

```python
def process(self) -> None:
    """
    Process method that creates and configures the PromptSummaryTool.

    This method:
    1. Gets the prompt driver from parameters, will be None if not provided
    2. Creates a PromptSummaryEngine with the prompt driver
    3. Creates a PromptSummaryTool with the engine
    4. Outputs the tool as a dictionary for later use
    """
    # Get the prompt driver from parameters, will be None if not provided
    prompt_driver = self.parameter_values.get("prompt_driver", None)

    if prompt_driver is None:
        msg = "Prompt driver is required for PromptSummaryTool."
        raise ValueError(msg)

    # Create the engine with the prompt driver (engine handles the summarization logic)
    engine = PromptSummaryEngine(prompt_driver=prompt_driver)

    # Create the tool with the engine (tool provides the interface for using the engine)
    tool = PromptSummaryTool(prompt_summary_engine=engine)

    # Store the tool as a dictionary in the output parameters for later use
    self.parameter_output_values["tool"] = tool
```

## Fields

- **prompt_driver**: A string representing the prompt driver for summarization.
    - Input type: String
    - Type: String
    - Output type: String
    - Default value: `default_prompt_driver` (use a default prompt driver if none provided)
    - Tooltip: Prompt driver for summarization (e.g., `'default_prompt_driver'`, `'custom_prompt_driver'`)

## Example Use Cases

- Summarize text using the default prompt driver.
```python
prompt_summary_tool_node = PromptSummaryToolNode("Text Summarizer")
prompt_summary_tool_node.process()
```

- Summarize text using a custom prompt driver.
```python
prompt_summary_tool_node = PromptSummaryToolNode("Custom Text Summarizer")
prompt_summary_tool_node.add_parameter(
    Parameter(
        name="prompt_driver",
        input_types=["str"],
        type="string",
        output_type="string",
        default_value="custom_prompt_driver",  # Use a custom prompt driver
        tooltip="Prompt driver for summarization (e.g., 'default_prompt_driver', 'custom_prompt_driver')",
    )
)
prompt_summary_tool_node.process()
```

## Troubleshooting

- If the `prompt_driver` parameter is not provided, an error message will be raised.
```python
try:
    prompt_summary_tool_node = PromptSummaryToolNode("Text Summarizer")
except ValueError as e:
    print(e)  # Output: "Prompt driver is required for PromptSummaryTool."
```

- If the `prompt_driver` parameter is invalid, an error message will be raised.
```python
try:
    prompt_summary_tool_node = PromptSummaryToolNode("Invalid Text Summarizer")
except ValueError as e:
    print(e)  # Output: "Prompt driver is required for PromptSummaryTool."
```