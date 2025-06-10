# GetListIsEmpty

## What is it?

The GetListIsEmpty node is a utility node that checks whether a list is empty or not. It provides a boolean output indicating if the input list contains any items.

## When would I use it?

Use the GetListIsEmpty node when:

- You need to check if a list has any items
- You want to validate that a list is not empty before processing
- You're building conditional workflows based on list content
- You need to ensure data is available before proceeding
- You want to monitor the state of dynamic lists

## How to use it

### Basic Setup

1. Add a GetListIsEmpty node to your workflow
1. Connect any list to the "items" input
1. The node will automatically check and output whether the list is empty

### Parameters

- **items**: The list to check (list input)
- **is_empty**: Boolean indicating if the list is empty (true) or not (false)

### Outputs

- **is_empty**: A boolean value (true if the list is empty, false if it contains items)

## Example

Imagine you want to check if a task list has any pending tasks:

1. Add a GetListIsEmpty node to your workflow
1. Connect your task list to the "items" input
1. The "is_empty" output will be true if there are no tasks, false if there are tasks

## Important Notes

- The node automatically updates when the input list changes
- If no list is connected, the output will be true (empty)
- The node works with lists of any type of items
- The output is always a boolean value

## Common Issues

- **No Input**: If no list is connected, the output will be true (empty)
- **Invalid Input**: If the input is not a list, the output will be true (empty)
- **Type Mismatch**: The node only works with list inputs, other types will result in true (empty)
