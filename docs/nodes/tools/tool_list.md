# ToolList

## What is it?

The ToolList node combines multiple tools into a single list. This allows you to connect directly to a "tools" input parameter.

## When would I use it?

Use this node when you want to:

- Combine multiple tools into a single list
- Create a workflow that leverages the strengths of different tools
- Integrate tools from various sources in your Griptape workflow

## How to use it

### Basic Setup

1. Add the ToolList to your workflow
1. Connect it to other nodes that provide necessary input parameters (e.g., tools)
1. Run the flow to see the combined list of tools

### Parameters

- **tools**: A list of tools to combine into a single list.

### Outputs

- **tool_list**: The combined list of tools.

## Example

Imagine you have a workflow that generates and saves text:

1. Create a flow with several nodes (like an agent that generates text and a node that saves it)
1. Add the ToolList, connecting it to nodes that provide tools parameters
1. Run the flow to see the combined list of tools in action

## Important Notes

- The ToolList requires input tools to be provided when running the flow.
- Using nested lists for tool inputs will result in flattened output.

## Common Issues

- **Invalid Input Tools**: Ensure that you're providing a valid list of tools when connecting this node to other nodes in your workflow.
- **Nested Lists**: Be aware that nested lists for tool inputs will be flattened into a single list.
