# KeyValuePair

## What is it?

The KeyValuePair is a simple building block that creates a single key-value pair and stores it in a dictionary. Think of it as creating a label (key) and attaching a piece of information (value) to it.

## When would I use it?

Use this node when you want to:

- Create a simple name-value association
- Define a single parameter with its value
- Add structured data to your workflow with just one key-value pair

## How to use it

### Basic Setup

1. Add the KeyValuePair to your workspace
1. Connect it to your flow

### Parameters

- **key**: The name or identifier for your value (e.g., "name", "temperature", "option")
- **value**: The information you want to associate with the key (e.g., "John", "72", "enabled")

### Outputs

- **dictionary**: A dictionary containing your single key-value pair

## Example

Imagine you want to create a setting for an image generation:

1. Add a KeyValuePair to your workflow
1. Set "key" to "image_style"
1. Set "value" to "watercolor"
1. The output dictionary will be: {"image_style": "watercolor"}

## Important Notes

- This node creates a dictionary with just one key-value pair
- Both the key and value can be multiline text if needed
- The key is usually a short identifier, while the value can be anything
- If you need multiple key-value pairs, consider using the DictNode instead
