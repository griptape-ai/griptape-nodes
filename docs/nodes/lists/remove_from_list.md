# RemoveFromList

## What is it?

The RemoveFromList node is a utility node that removes items from an existing list based on different criteria. It can remove items by their position (first, last, or specific index) or by matching a specific item value.

## When would I use it?

Use the RemoveFromList node when:

- You need to remove items from an existing list
- You want to filter out specific items from a collection
- You're maintaining dynamic lists that need items removed during workflow execution
- You need to clean up or modify lists by removing unwanted elements
- You want to extract items from specific positions in a list

## How to use it

### Basic Setup

1. Add a RemoveFromList node to your workflow
1. Connect an existing list to the "items" input
1. Choose how to remove items using the "remove_item_by" parameter
1. Depending on the removal method, provide either an index or item value
1. The output will be the list with the specified item removed

### Parameters

- **items**: The list to remove items from (list input)
- **remove_item_by**: How to remove the item (choices: "first", "last", "index", "item")
- **item**: The specific item to remove (only visible when remove_item_by is "item")
- **index**: The position to remove from (only visible when remove_item_by is "index")
- **output**: The modified list with the item removed

### Outputs

- **output**: The list containing the original items minus the removed item

## Example

Imagine you want to remove a specific task from a list of tasks:

1. Add a RemoveFromList node to your workflow
1. Connect your task list to the "items" input
1. Set "remove_item_by" to "item"
1. Connect the task you want to remove to the "item" input
1. The output will be the original list with the specified task removed

## Important Notes

- The node creates a new list rather than modifying the original
- When using "index" removal, the index must be within the list's bounds
- When using "item" removal, the item must exist in the list
- The "index" and "item" parameters are only visible when their respective removal methods are selected

## Common Issues

- **Invalid Index**: If using "index" removal, ensure the index is within the list's bounds
- **Item Not Found**: When using "item" removal, the item must exist in the list
- **Empty List**: If the input list is empty, no items can be removed
- **Type Mismatch**: When using "item" removal, ensure the item type matches the list items
