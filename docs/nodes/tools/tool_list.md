# ToolListNode

## What is it?

The ToolListNode is a custom node in Griptape that allows you to combine multiple tools into a single list. This enables more complex workflows by providing agents with access to a diverse set of tools.

## When would I use it?

Use this node when you want to:

- Combine multiple tools into a single list
- Create a workflow that leverages the strengths of different tools
- Integrate tools from various sources in your Griptape workflow

## How to use it

### Basic Setup

1. Add the ToolListNode to your workspace
1. Connect it to other nodes that provide necessary input parameters (e.g., tools)
1. Run the flow to see the combined list of tools

### Fields

- **tools**: A list of tools to combine into a single list.
  - Input type: List of objects
  - Allowed modes: INPUT
  - Default value: Empty list
  - Tooltip: List of tools to combine

### Outputs

- **tool_list**: The combined list of tools.
  - Output type: List of objects
  - Allowed modes: OUTPUT
  - Default value: Empty list
  - Tooltip: Combined list of tools

## Example

Imagine you have a workflow that generates and saves text:

1. Create a flow with several nodes (like an agent that generates text and a node that saves it)
1. Add the ToolListNode at the end of your sequence, connecting it to nodes that provide tools parameters
1. Run the flow to see the combined list of tools in action

## Important Notes

- The ToolListNode requires input tools to be provided when running the flow.
- Using nested lists for tool inputs will result in flattened output.

## Validation

The `process` method checks for the following:

- If no tools are provided, it returns an empty list of exceptions.
- If the input tools are not a list, it raises a ValueError.

## Common Issues

- **Invalid Input Tools**: Ensure that you're providing a valid list of tools when connecting this node to other nodes in your workflow.
- **Nested Lists**: Be aware that nested lists for tool inputs will be flattened into a single list.
