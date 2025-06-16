# GetIndexOfItem

## What is it?

The GetIndexOfItem node is a utility node that finds the position (index) of a specific item in a list. It returns the zero-based index of the first occurrence of the item in the list.

## When would I use it?

Use the GetIndexOfItem node when:

- You need to find the position of an item in a list
- You want to locate specific items in a collection
- You're building workflows that need to reference items by their position
- You need to validate item positions in lists
- You want to track the location of items in dynamic lists

## How to use it

### Basic Setup

1. Add a GetIndexOfItem node to your workflow
1. Connect a list to the "items" input
1. Connect the item you want to find to the "item" input
1. The node will output the index of the item in the list

### Parameters

- **items**: The list to search in (list input)
- **item**: The item to find in the list (any type)
- **index**: The position of the item in the list (integer output)

### Outputs

- **index**: An integer representing the position of the item (-1 if not found)

## Example

Imagine you want to find the position of a specific task in a task list:

1. Add a GetIndexOfItem node to your workflow
1. Connect your task list to the "items" input
1. Connect the task you want to find to the "item" input
1. The "index" output will show the position of the task in the list

## Important Notes

- The node returns -1 if the item is not found in the list
- Index positions start at 0 (first item is at index 0)
- The node finds the first occurrence of the item if it appears multiple times
- The node automatically updates when either the list or the item changes

## Common Issues

- **Item Not Found**: If the item is not in the list, the output will be -1
- **No Input**: If either the list or item is not connected, the output will be -1
- **Invalid Input**: If the input is not a list, the output will be -1
- **Type Mismatch**: The item type must match the list item types for proper comparison
- **Case Sensitivity**: String comparisons are case-sensitive
