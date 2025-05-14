# Dictionary

## What is it?

The Dictionary node lets you create a dictionary (a collection of key-value pairs) by providing separate lists of keys and values. It's a simple way to organize related data with named values that can be used throughout your workflow.

## When would I use it?

Use this node when you want to:

- Organize related data with named values
- Create structured data to pass to other nodes
- Build configuration settings for other components
- Prepare data in a format that's easy to access by key
- Combine multiple values into a single organized structure

## How to use it

### Basic Setup

1. Add the Dictionary node to your workflow
1. Set up your lists of keys and values
1. Connect the dictionary output to other nodes that need structured data

### Parameters

- **keys**: A list of strings that will be used as dictionary keys
- **values**: A list of values (strings, numbers, booleans, etc.) that correspond to each key

### Outputs

- **dict**: The constructed dictionary containing all key-value pairs

## Example

Imagine you want to create a configuration dictionary for a user profile:

1. Add a Dictionary node to your workflow
1. Set the "keys" parameter to:
    ```
    ["name", "age", "premium_member", "interests"]
    ```
1. Set the "values" parameter to:
    ```
    ["Jane Smith", 32, true, ["hiking", "photography", "coding"]]
    ```
1. The output dictionary will be:
    ```
    {"name": "Jane Smith", "age": 32, "premium_member": true, "interests": ["hiking", "photography", "coding"]}
    ```
1. Connect this dictionary to other nodes that need user profile information

## Important Notes

- Keys are automatically converted to strings
- If you provide more keys than values, the extra keys will be assigned `None` values
- Empty or `None` keys are skipped unless it's the only key and has a value
- You can provide single values instead of lists, and they'll be converted to single-item lists
- The node works with various value types including strings, numbers, booleans, and nested lists
- The dictionary format is compatible with nodes that accept dictionary inputs

## Common Issues

- **Mismatched Lists**: If your keys and values lists have different lengths, some keys may have `None` values or some values may be ignored
- **Key Conversion**: All keys are converted to strings, which may cause unexpected behavior if you're using complex objects as keys
- **Empty Keys**: Empty strings or `None` values used as keys may be skipped depending on their values
