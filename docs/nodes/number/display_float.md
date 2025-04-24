# DisplayFloat

## What is it?

The DisplayFloat node simply displays a float parameter.

## When would I use it?

When you want to inspect a floating-point number value in your graph

## How to use it

### Basic Setup

1. Add the DisplayFloat to your workflow
1. Connect any other node's float output to this input

### Parameters

- **float**: A single floating-point number that is displayed by this node (default is 0.0)

### Outputs

- **None**

## Example

Imagine you want to visualize the temperature setting used in your workflow:

1. Add a DisplayFloat to your workflow
1. Connect the "temperature" output from another node to the DisplayFloat's input
1. The DisplayFloat will now show the current temperature value in your graph

## Important Notes

- This node is for visualization purposes only
- It doesn't modify the value, just displays it
- Useful for debugging and monitoring your workflow

## Common Issues

- None
