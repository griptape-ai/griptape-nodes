# Bool Input

## What is it?

The Bool Input node is a simple way to input boolean values for use in workflows.

## When would I use it?

Use the Bool Input node when:

- You need to create boolean values (True/False)
- You want to prepare boolean input for other nodes in your workflow
- You need to define conditions or flags for workflow control
- You're building workflows that require boolean decision points

## How to use it

### Basic Setup

1. Add a Bool Input node to your workflow
1. Set the "value" parameter to either True or False
1. Connect the output to nodes that accept boolean input

### Parameters

- **value**: The boolean value (bool, defaults to True)

### Outputs

- **bool**: The boolean value as a bool

## Example

A workflow to control a conditional branch:

1. Add a Bool Input node to your workflow
1. Set the "value" parameter to `True`
1. Connect the output to a Conditional node's condition parameter

## Important Notes

- The node supports both True and False values
- The value can be set through both input and property modes
- The output updates in real-time when the input value changes

## Common Issues

- Confusion between string "true"/"false" and boolean True/False values
- Unexpected behavior when connecting to nodes expecting different types
