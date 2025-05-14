# DisplayText

## What is it?

The DisplayText node simply displays text content in your workflow.

## When would I use it?

Use the DisplayText node when:

- You need to display results or information in your workflow
- You want to show text output from previous processing steps
- You need a placeholder for text content that will be updated during workflow execution
- You want to create readable labels or descriptions within your workflow
- You need to visualize string data at specific points in your process

## How to use it

### Basic Setup

1. Add a DisplayText node to your workflow
1. Set the initial text value if desired
1. Connect inputs to the text parameter or manually enter text
1. Connect the text output to other nodes that require text input

### Parameters

- **text**: The text content to display (string input, supports multiline text)

### Outputs

- **text**: The same text content, available as output to connect to other nodes

## Example

Imagine you're building a workflow that processes and displays information:

1. Add a DisplayText node to your workflow
1. Connect the output from a RunAgent node to the DisplayText node's text parameter
1. When the workflow runs, the AI-generated content will replace the initial text

## Important Notes

- The DisplayText node is for visualization and doesn't modify the text content
- The node passes through text exactly as received, without any processing or formatting
