# GetListLength

## What is it?

The GetListLength node is a utility node that calculates and outputs the number of items in a list. It provides a simple way to determine the size of any list in your workflow.

## When would I use it?

Use the GetListLength node when:

- You need to know how many items are in a list
- You want to check if a list is empty or has a specific number of items
- You're building workflows that depend on list size
- You need to validate list lengths before processing
- You want to monitor the size of dynamic lists

## How to use it

### Basic Setup

1. Add a GetListLength node to your workflow
1. Connect any list to the "items" input
1. The node will automatically calculate and output the list's length

### Parameters

- **items**: The list to measure (list input)
- **length**: The number of items in the list (integer output)

### Outputs

- **length**: An integer representing the number of items in the input list

## Example

Imagine you want to check how many tasks are in a task list:

1. Add a GetListLength node to your workflow
1. Connect your task list to the "items" input
1. The "length" output will show the total number of tasks in the list

## Important Notes

- The node automatically updates the length when the input list changes
- If the input list is empty or not provided, the length will be 0
- The length is always a non-negative integer
- The node works with lists of any type of items

## Common Issues

- **Empty List**: If no list is connected, the length will be 0
- **Invalid Input**: If the input is not a list, the length will be 0
- **Type Mismatch**: The node only works with list inputs, other types will result in a length of 0
