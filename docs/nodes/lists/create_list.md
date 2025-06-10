# CreateList

## What is it?

The CreateList node is a utility node that creates a list from provided items. It allows you to build lists dynamically in your workflow by combining multiple inputs into a single list output.

## When would I use it?

Use the CreateList node when:

- You need to combine multiple items into a single list
- You want to create a list from various inputs in your workflow
- You're building data structures that require list format
- You need to prepare data for nodes that require list inputs
- You want to consolidate multiple values into a single list structure

## How to use it

### Basic Setup

1. Add a CreateList node to your workflow
1. Connect individual items to the "items" input or add them directly in the node's properties
1. The node will combine all inputs into a single list output

### Parameters

- **items**: A list of items to combine (supports multiple inputs of any type)
- **output**: The combined list containing all input items

### Outputs

- **output**: A list containing all the items provided as input

## Example

Imagine you want to create a list of different data types:

1. Add a CreateList node to your workflow
1. Connect various inputs to the "items" parameter (e.g., text, numbers, or other data types)
1. The output will be a list containing all these items in the order they were connected

## Important Notes

- The CreateList node can handle items of any type
- Items are added to the list in the order they are connected
- The node automatically updates its output whenever input items change
- You can add items both through connections and directly in the node's properties

## Common Issues

- **Empty List**: If no items are provided, the output will be an empty list
- **Type Mismatch**: The node accepts items of any type, but be aware of how the receiving node handles different data types
