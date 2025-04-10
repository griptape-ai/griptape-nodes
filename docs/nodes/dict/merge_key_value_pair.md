# MergeKeyValuePair Node

## What is it?

The `MergeKeyValuePair` node merges multiple key-value pairs into a single dictionary. It takes in four input parameters, each representing a key-value pair to be merged together.

## When would I use it?

Use this node when you need to combine multiple sets of key-value pairs into a single, unified dictionary. This can be useful for tasks such as data aggregation, configuration merging, or data normalization.

## How to use it

### Basic Setup

1. Add the `MergeKeyValuePair` node to your workflow.
1. Connect four input parameters to the node:
    - `key_value_pair_1`
    - `key_value_pair_2`
    - `key_value_pair_3`
    - `key_value_pair_4`

These inputs should be dictionaries containing key-value pairs.

### Parameters

- **`key_value_pair_1`, `key_value_pair_2`, `key_value_pair_3`, and `key_value_pair_4`**: These are the input parameters that represent the key-value pairs to be merged together. Each parameter is a dictionary with two values: a key and a value.

### Outputs

- **`output`** is a dictionary containing the merged key-value pairs.

## Example

Imagine you're working with configuration data from multiple sources. You have four sets of configuration data, each represented as a dictionary:

```python
config1 = {"database": "mysql", "host": "localhost"}
config2 = {"database": "postgres", "port": 5432}
config3 = {"database": "sqlite", "username": "admin"}
config4 = {"database": "oracle", "password": "secret"}
```

You can use the `MergeKeyValuePair` node to merge these configurations into a single dictionary:

1. Connect the four input parameters (`key_value_pair_1`, `key_value_pair_2`, `key_value_pair_3`, and `key_value_pair_4`) to the `MergeKeyValuePair` node.
1. Set the values of each parameter to the corresponding configuration data.

The output will be a single dictionary containing all the key-value pairs:

```python
merged_config = {
    "database": "mysql",
    "host": "localhost",
    "port": 5432,
    "username": "admin",
    "password": "secret"
}
```

## Important Notes

- The `MergeKeyValuePair` node assumes that all input parameters are dictionaries with two values: a key and a value.
- If any of the input parameters are missing or empty, they will be ignored in the merge process.
- The output dictionary contains only the key-value pairs from the non-empty input parameters.
