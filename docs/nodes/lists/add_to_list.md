# AddToList

## What is it?

The AddToList node is a utility node that adds an item to an existing list at a specified position. It allows you to insert new items into lists at the beginning, end, or at a specific index.

## When would I use it?

Use the AddToList node when:

- You need to add new items to an existing list
- You want to insert items at specific positions in a list
- You're building dynamic lists that need to be updated during workflow execution
- You need to maintain ordered collections of items
- You want to modify lists without creating new ones

## How to use it

### Basic Setup

1. Add an AddToList node to your workflow
1. Connect an existing list to the "items" input
1. Connect the item you want to add to the "item" input
1. Choose where to add the item using the "position" parameter
1. If using "index" position, specify the index value

### Parameters

- **items**: The list to add the item to (list input)
- **item**: The item to add to the list (any type)
- **position**: Where to add the item (choices: "start", "end", "index")
- **index**: The specific position to add the item (only visible when position is "index")
- **output**: The modified list with the new item added

### Outputs

- **output**: The list containing the original items plus the newly added item

## Example

Imagine you want to add a new item to a list of tasks:

1. Add an AddToList node to your workflow
1. Connect your existing task list to the "items" input
1. Connect the new task to the "item" input
1. Set "position" to "end" to add it at the end of the list
1. The output will be the original list with the new task appended

## Important Notes

- The node creates a new list rather than modifying the original
- When using "index" position, the index must be within the list's bounds
- The "index" parameter is only visible when "position" is set to "index"
- Items can be of any type, but be aware of type compatibility with the receiving node

## Common Issues

- **Invalid Index**: If using "index" position, ensure the index is within the list's bounds
- **Empty List**: If the input list is empty, the item will be added as the first element
- **Type Mismatch**: Be aware of how the receiving node handles different data types in the list
