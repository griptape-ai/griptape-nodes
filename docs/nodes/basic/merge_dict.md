# MergeDict

## What is it?

The MergeDict is a building block that combines multiple dictionaries (collections of key-value pairs) into a single dictionary. Think of it as taking several labeled containers and pouring their contents into one larger container.

## When would I use it?
Use this node when you want to:
- Combine data from multiple sources
- Build a larger dictionary from smaller pieces
- Create a complete set of parameters from different parts of your workflow

## How to use it

### Basic Setup

1. Add the MergeDict to your workspace
1. Connect it to your flow
1. Connect a list of dictionaries to the input

### Required Fields
- **inputs**: A list of dictionaries to merge together

### Outputs
- **merged_dict**: The combined dictionary containing all key-value pairs from the input dictionaries

## Example
Imagine you have three dictionaries:
- Dict1: {"name": "Alice", "age": 30}
- Dict2: {"city": "New York", "country": "USA"}
- Dict3: {"age": 31, "occupation": "Engineer"}

When merged, the result would be:
{"name": "Alice", "age": 31, "city": "New York", "country": "USA", "occupation": "Engineer"}

Notice that "age" from Dict3 overwrote "age" from Dict1 because Dict3 came later in the list.

## Important Notes
- When the same key appears in multiple dictionaries, the value from the later dictionary wins
- The order of dictionaries in the input list matters - later dictionaries override earlier ones
- Non-dictionary items in the input list are ignored
- This node only does a shallow merge (it doesn't combine nested dictionaries)

## Common Issues
- **Unexpected Values**: Check the order of your dictionaries if values are being overwritten unexpectedly
- **Invalid Inputs**: Make sure you're providing a list of dictionaries to the inputs parameter