# DisplayList

## What is it?

The DisplayList node is a utility node that takes a list as input and creates individual output parameters for each item in the list. It automatically determines the type of each item and creates appropriately typed output parameters.

## When would I use it?

Use the DisplayList node when:

- You need to access individual items from a list separately
- You want to display or process list items individually
- You're working with lists of mixed types and need type-specific handling
- You need to connect list items to different nodes
- You want to visualize the contents of a list in a more detailed way

## How to use it

### Basic Setup

1. Add a DisplayList node to your workflow
1. Connect a list to the "items" input
1. The node will automatically create output parameters for each item
1. Connect the individual item outputs to other nodes as needed

### Parameters

- **items**: The list to display (list input)
- **item_0, item_1, etc.**: Dynamic output parameters for each item in the list

### Outputs

- **item_0, item_1, etc.**: Individual outputs for each item in the list, with types matching the items

## Example

Imagine you have a list of mixed data types that you want to process separately:

1. Add a DisplayList node to your workflow
1. Connect your list to the "items" input
1. The node will create separate outputs for each item
1. Connect each output to the appropriate processing node based on its type

## Important Notes

- The node automatically determines the type of each item
- Output parameters are created dynamically based on the list contents
- Supported types include: string, boolean, integer, float, and image artifacts
- The node updates its outputs whenever the input list changes
- Output parameters are named sequentially (item_0, item_1, etc.)

## Common Issues

- **Empty List**: If the input list is empty, no output parameters will be created
- **Invalid Input**: If the input is not a list, no output parameters will be created
- **Type Limitations**: Some complex types may be handled as "any" type
- **Dynamic Updates**: The number of output parameters changes with the list length
