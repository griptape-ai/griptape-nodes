# DisplayInteger

## What is it?

The DisplayInteger node simply displays an integer parameter.

## When would I use it?

Use this node/class when you want to:

- When you want to inspect an integer value in your graph

## How to use it

### Basic Setup

1. Add the DisplayInteger to your workflow
1. Connect any other node's integer output to this input

### Parameters

- **integer**: A single integer value that is displayed by this node (default is 0)

### Outputs

- **None**

## Example

Imagine you want to visualize the token count used in your workflow:

1. Add a DisplayInteger to your workflow
1. Connect the "token_count" output from another node to the DisplayInteger's input
1. The DisplayInteger will now show the current token count in your graph

## Important Notes

- This node is for visualization purposes only
- It doesn't modify the value, just displays it
- Useful for debugging and monitoring your workflow

## Common Issues

- None
