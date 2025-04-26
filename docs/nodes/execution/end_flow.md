# EndFlowNode

## What is it?

The EndFlowNode is a simple building block that marks the end of your workflow. Think of it as a stop sign that tells the system "the flow ends here."

## When would I use it?

Use this node when you want to:

- Clearly mark where your workflow ends
- Create a visual endpoint for your flow
- Ensure your workflow has a proper ending point

## How to use it

### Basic Setup

1. Add the EndFlowNode to your workflow
1. Connect it to the end of your flow

### Parameters

- **control**: This is an input connection point for the flow (you connect other nodes to this)

### Outputs

- **None** - this node doesn't output anything, it just marks the end of the flow

## Example

Imagine you have a workflow that generates and saves text:

1. Create a flow with several nodes (like an agent that generates text and a node that saves it)
1. Add an EndFlowNode at the end of your sequence
1. Connect the last active node in your flow to the EndFlowNode

## Important Notes

- The EndFlowNode doesn't actually do anything - it's just a marker for readability
- You can have multiple EndFlowNodes in complex workflows with different branches
- Using EndFlowNodes makes your workflows easier to understand

## Common Issues

- **Flow Continues Past EndFlowNode**: Make sure you're not connecting anything after the EndFlowNode
- **Flow Doesn't Reach EndFlowNode**: Check your connections to ensure the flow can reach the end
