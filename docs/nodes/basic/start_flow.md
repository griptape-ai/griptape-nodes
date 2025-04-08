# StartFlow

## What is it?

The StartFlow is a special building block that marks the beginning of your workflow. Think of it as the "Go" sign that tells the system where to start running your flow.

## When would I use it?
Use this node when you want to:
- Create a clear starting point for your workflow
- Begin a sequence of connected nodes
- Define the entry point for your flow

## How to use it

### Basic Setup

1. Add the StartFlow to your workspace (it may be added automatically when you create a new workflow)
1. Connect it to the first action node in your flow

### Fields
- **control**: This is an output connection point for the flow (you connect this to other nodes)

### Outputs
- None specific - this node just passes control to the next node in the flow

## Example
Imagine you're creating a workflow that generates and saves text:

1. Start with a StartFlow
1. Connect it to a RunAgent that will generate text
1. Connect that to a SaveText to save the generated text
1. Connect that to an EndFlowNode to complete the flow

The StartFlow tells the system "start here and follow the connections."

## Important Notes

- Every workflow needs exactly one StartFlow
- The StartFlow doesn't take any inputs - it's just a starting point
- You can only have one StartFlow per workflow
- The StartFlow is typically added automatically when you create a new workflow

## Common Issues

- **Flow Doesn't Run**: Make sure your StartFlow is properly connected to the next node
- **Multiple Start Points**: Ensure you only have one StartFlow in your workflow
