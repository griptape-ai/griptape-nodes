# GetListContainsItem

## What is it?

The GetListContainsItem node is a utility node that checks whether a specific item exists in a list. It provides a boolean output indicating if the item is found in the input list.

## When would I use it?

Use the GetListContainsItem node when:

- You need to check if a specific item exists in a list
- You want to validate that required data is present in a collection
- You're building conditional workflows based on item presence
- You need to filter or process lists based on item existence
- You want to monitor for specific items in dynamic lists

## How to use it

### Basic Setup

1. Add a GetListContainsItem node to your workflow
1. Connect a list to the "items" input
1. Connect the item you want to check for to the "item" input
1. The node will automatically check and output whether the item exists in the list

### Parameters

- **items**: The list to check (list input)
- **item**: The item to look for in the list (any type)
- **contains_item**: Boolean indicating if the item was found (true) or not (false)

### Outputs

- **contains_item**: A boolean value (true if the item is found, false if not)

## Example

Imagine you want to check if a specific task exists in a task list:

1. Add a GetListContainsItem node to your workflow
1. Connect your task list to the "items" input
1. Connect the task you want to check for to the "item" input
1. The "contains_item" output will be true if the task is found, false if not

## Important Notes

- The node automatically updates when either the list or the item changes
- If either the list or item is not provided, the output will be false
- The node uses exact matching to find items
- The output is always a boolean value

## Common Issues

- **No Input**: If either the list or item is not connected, the output will be false
- **Invalid Input**: If the input is not a list, the output will be false
- **Type Mismatch**: The item type must match the list item types for proper comparison
- **Case Sensitivity**: String comparisons are case-sensitive
