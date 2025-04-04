# RagToolNode

## What is it?

The RagToolNode is a custom node in Griptape that utilizes the Rag Tool to process and generate text. It's designed to work seamlessly with other nodes in the Griptape workflow.

## When would I use it?

Use this node when you want to:

- Leverage the capabilities of the Rag Tool for text processing
- Integrate the Rag Tool with other nodes in your workflow
- Create a custom ruleset for the Rag Tool

## How to use it

### Basic Setup

1. Add the RagToolNode to your workspace
1. Connect it to other nodes that provide necessary input parameters (e.g., description, off_prompt, rag_engine)

### Fields

- **description**: The text description of the tool. If not provided, defaults to "Contains information."
- **off_prompt**: A boolean indicating whether to use an off-prompt for the Rag Tool.
- **rag_engine**: The engine used by the Rag Tool. Required.

### Outputs

- **tool**: The created RagTool instance
- **rules**: The created Ruleset instance

## Example

Imagine you have a workflow that generates and saves text:

1. Create a flow with several nodes (like an agent that generates text and a node that saves it)
1. Add the RagToolNode at the end of your sequence, connecting it to nodes that provide description, off_prompt, and rag_engine parameters
1. Run the flow to see the Rag Tool in action

## Important Notes

- The RagToolNode requires the rag_engine parameter to be set.
- Using the RagToolNode with an invalid or missing rag_engine will raise a ValueError.

## Common Issues

- **Rag Engine Not Provided**: Ensure that you're providing the required rag_engine parameter when connecting this node to other nodes in your workflow.
- **Incorrect Tool Output**: Verify that the tool and rules outputs are correctly set up for use in downstream nodes.
