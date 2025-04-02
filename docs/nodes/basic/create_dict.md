# DictNode

## What is it?
The DictNode is a building block that lets you create a dictionary (a collection of key-value pairs). Think of it as creating a labeled container where each item has both a name (key) and a value.

## When would I use it?
Use this node when you want to:
- Organize data with named values
- Create a structured collection of related information
- Pass multiple values as a single unit to other nodes

## How to use it

### Basic Setup
1. Add the DictNode to your workspace
2. Connect it to your flow
3. Set up your keys and values

### Required Fields
- **keys**: A list of names or labels for your values
- **values**: A list of values that correspond to each key

### Outputs
- **dict**: The completed dictionary that can be used by other nodes

## Example
Imagine you want to create a dictionary with information about a person:

1. Set "keys" to ["name", "age", "city"]
2. Set "values" to ["Alice", 28, "New York"]
3. The output dictionary will be: {"name": "Alice", "age": 28, "city": "New York"}

## Important Notes
- The keys and values lists should be the same length - each key needs a corresponding value
- Keys will be converted to strings (if possible) since dictionary keys are typically strings
- Empty or None keys will be skipped (unless it's the only key and has a value)
- If there are more keys than values, the extra keys will get None values

## Common Issues
- **Mismatched Lists**: Make sure your keys and values lists are the same length
- **Invalid Keys**: Dictionary keys must be strings, so make sure keys can be converted to strings
- **Empty Dictionary**: Check that you've provided valid keys and values