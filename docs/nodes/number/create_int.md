# CreateInteger

## What is it?

The CreateInteger is a simple building block that creates a single integer value. Think of it as a way to define and store a whole number that can be used throughout your workflow.

## When would I use it?

Use this node when you want to:

- Define a whole number value without decimals
- Create a configurable integer parameter for your workflow
- Set up counters, indices, or quantity values
- Establish limits, thresholds, or other whole-number values

## How to use it

### Basic Setup

1. Add the CreateInteger to your workspace
2. Set your desired integer value
3. Connect it to your flow

### Parameters

- **integer**: A whole number value (default is 0)

### Outputs

- **integer**: The integer value that can be used by other nodes

## Example

Imagine you want to set a maximum token limit for an AI response:

1. Add a CreateInteger to your workflow
2. Set the "integer" value to 500
3. Connect the output to a model's max_tokens parameter
4. The AI model will now limit its responses to 500 tokens

## Important Notes

- This node creates a single integer value
- The default value is 0 if none is specified
- You can update the value through the node's properties
- Integers represent whole numbers like 1, 42, -7, or 0