# Combine Lists

The Combine Lists node takes two lists and combines them into a single flattened list.

## Inputs

- **List A** (list): The first list to combine
- **List B** (list): The second list to combine

## Outputs

- **Output** (list): The combined list containing all items from both input lists in order

## Example

```python
# List A: [1, 2]
# List B: [3, 4]
# Output: [1, 2, 3, 4]

# List A: ["a", "b"]
# List B: ["c", "d"]
# Output: ["a", "b", "c", "d"]

# List A: [1, 2]
# List B: []
# Output: [1, 2]
```

## Notes

- The order of items is preserved in the output list
- If either input is not a list, it will be treated as an empty list
- The original lists are not modified; a new list is returned
- The operation is equivalent to list concatenation (list_a + list_b)
