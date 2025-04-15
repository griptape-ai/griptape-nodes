# KeyValuePair Node

## What is it?

The `KeyValuePair` node creates a simple dictionary containing a single key-value pair. It takes a key and a value as inputs and outputs a dictionary with that single mapping.

## When would I use it?

Use the KeyValuePair node when:

- You need to create a simple dictionary with a single key-value association
- You want to dynamically generate configuration parameters
- You're building data structures piece by piece
- You need to transform two separate values into a dictionary format
- You're preparing data for nodes that require dictionary inputs

## How to use it

### Basic Setup

1. Add the KeyValuePair node to your workflow
1. Set the "key" parameter to your desired dictionary key
1. Set the "value" parameter to the value you want associated with that key
1. Connect the "dictionary" output to other nodes that require dictionary input

### Parameters

- **key**: The string that will be used as the dictionary key (string)
- **value**: The string that will be associated with the key (string, supports multiline text)

### Outputs

- **dictionary**: A dictionary containing the single key-value pair

## Example

Imagine you're creating a workflow that needs to set configuration options:

1. Add a KeyValuePair node to your workflow
1. Set the "key" parameter to "max_tokens"
1. Set the "value" parameter to "1024"
1. Connect the "dictionary" output to a node that requires configuration parameters

The output will be a dictionary: `{"max_tokens": "1024"}`

This dictionary can then be used by other nodes in your workflow that need this configuration parameter.

## Important Notes

- Both the key and value are treated as strings in this node
- The value parameter supports multiline text for longer content
- If you need to create a dictionary with multiple key-value pairs, you can use multiple KeyValuePair nodes and combine their outputs with a merge node
