# MergeKeyValuePair Node

## What is it?

The `MergeKeyValuePair` node merges multiple dictionaries into a single dictionary. It takes up to four input dictionaries and combines them into one unified output dictionary.

## When would I use it?

Use the MergeKeyValuePair node when:

- You need to combine multiple dictionaries into a single dictionary
- You're working with separate configuration settings that need to be unified
- You want to aggregate data from different sources into one structure
- You're building complex parameter sets from individual components
- You need to consolidate related key-value pairs from different parts of your workflow

## How to use it

### Basic Setup

1. Add the MergeKeyValuePair node to your workflow
1. Connect up to four dictionary outputs from other nodes to the inputs of this node
1. The node will combine all input dictionaries into a single output dictionary

### Parameters

- **key_value_pair_1**: First dictionary to merge (dictionary input)
- **key_value_pair_2**: Second dictionary to merge (dictionary input)
- **key_value_pair_3**: Third dictionary to merge (dictionary input)
- **key_value_pair_4**: Fourth dictionary to merge (dictionary input)

### Outputs

- **output**: A single dictionary containing all key-value pairs from the input dictionaries

## Example

Imagine you're building a workflow that needs to combine configuration settings from different sources:

1. Add a MergeKeyValuePair node to your workflow
1. Connect a dictionary with database settings to "key_value_pair_1" (e.g., {"host": "localhost", "port": 5432})
1. Connect a dictionary with authentication settings to "key_value_pair_2" (e.g., {"username": "admin", "password": "secure123"})
1. Connect a dictionary with application settings to "key_value_pair_3" (e.g., {"app_name": "MyApp", "debug": true})
1. The output will be a single dictionary containing all these settings: {"host": "localhost", "port": 5432, "username": "admin", "password": "secure123", "app_name": "MyApp", "debug": true}

## Important Notes

- If the same key appears in multiple input dictionaries, the value from the later dictionary will overwrite earlier values
- The node ignores any inputs that are not dictionaries or are None
- You don't need to connect all four inputs - the node works with any number of inputs from one to four
- The order of inputs matters when there are key conflicts
