# DisplayDictionary Node

## What is it?

The `DisplayDictionary` node is a utility node that displays the contents of a dictionary in your workflow. It provides a visual representation of dictionary data, making it easier to inspect and debug dictionary values during workflow execution.

## When would I use it?

Use the DisplayDictionary node when:

- You need to inspect the contents of a dictionary in your workflow
- You want to visualize complex data structures for debugging purposes
- You need to monitor how dictionary values change throughout your workflow
- You're working with JSON-like data and need to see its structure clearly

## How to use it

### Basic Setup

1. Add the DisplayDictionary node to your workflow
1. Connect any node that outputs a dictionary to the "dictionary" input of this node
1. The dictionary content will be displayed in the node's interface

### Parameters

- **dictionary**: The dictionary to be displayed (input/output parameter)
- **dictionary_display**: A string representation of the dictionary content (property parameter, displayed in the UI)

### Outputs

- **dictionary**: The same dictionary that was provided as input (passed through)

## Example

Imagine you're working with a workflow that processes user data:

1. Add a DisplayDictionary node to your workflow
1. Connect the output of a node that produces user data (like a database query or API response) to the "dictionary" input
1. The DisplayDictionary node will show the user data structure in a readable format
1. You can continue your workflow by connecting the "dictionary" output to other nodes that need this data

## Important Notes

- The DisplayDictionary node doesn't modify the dictionary data, it simply displays it
- The multiline text area in the node's UI makes it easier to read complex nested dictionaries
- This node is particularly useful for debugging and understanding data flow in your workflows

## Common Issues

- None
