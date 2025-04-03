# StringListNode

## What is it?

The StringListNode is a simple building block that creates or passes through a list of text strings. Think of it as a collection box where you can store multiple pieces of text together as a single unit.

## When would I use it?

Use this node when you want to:

- Create a list containing multiple text items
- Pass multiple strings as a single list to other nodes
- Collect related text strings together

## How to use it

### Basic Setup

1. Add the StringListNode to your workspace
1. Connect it to your flow

### Fields

- **string_list**: A list of strings (text items) or a single string that will be converted to a one-item list

### Outputs

- **string_list**: The list of strings that can be used by other nodes

## Example

Imagine you want to create a list of options for an agent to choose from:

1. Add a StringListNode to your workflow
1. Set the "string_list" to ["Option A", "Option B", "Option C"]
1. Connect the "string_list" output to another node that needs this list of options

If you input a single string like "Hello", it will be converted to a one-item list: ["Hello"]

## Important Notes

- This node can take either a single string or a list of strings as input
- If you provide a single string, it will be converted to a list with one item
- This node simply passes the list through - it doesn't process or change the content
- You can use this node to collect strings from different parts of your workflow

## Common Issues

- **Not a List**: If you expected a list but got something else, check what you're connecting to the input
- **Empty List**: Make sure you've provided valid input to the node
