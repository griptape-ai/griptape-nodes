# CreateFloat

## What is it?

The CreateFloat is a simple building block that creates a single floating-point number value. Think of it as a way to define and store a decimal number that can be used throughout your workflow.

## When would I use it?

Use this node when you want to:

- Define a numerical value with decimal precision
- Create a configurable number parameter for your workflow
- Set up values for mathematical operations
- Establish thresholds, rates, or other decimal values

## How to use it

### Basic Setup

1. Add the CreateFloat to your workspace
1. Set your desired float value
1. Connect it to your flow

### Parameters

- **float**: A floating-point number value (default is 0.0)

### Outputs

- **float**: The floating-point value that can be used by other nodes

## Example

Imagine you want to set a temperature value for an AI model:

1. Add a CreateFloat to your workflow
1. Set the "float" value to 0.7
1. Connect the output to a model's temperature parameter
1. The AI model will now use 0.7 as its temperature setting

## Important Notes

- This node creates a single floating-point value
- The default value is 0.0 if none is specified
- You can update the value through the node's properties
- Floating-point numbers can represent decimal values like 0.5, 3.14159, or -2.75

## Common Issues

- None
