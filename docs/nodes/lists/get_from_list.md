# Get From List

The Get From List node takes a list and an index as input and returns the item at that index in the list.

## Inputs

- **items** (list): The list to get an item from
- **index** (int): The index to get the item from

## Outputs

- **item** (any): The item at the specified index in the list. Returns None if the index is invalid or inputs are missing.

## Example

```python
# Input list: [1, 2, 3, 4, 5]
# Input index: 2
# Output: 3
```

## Notes

- If the index is out of range or invalid, the node will return None
- If either the list or index input is missing, the node will return None
- The output type is "any" since the list can contain items of any type
- The index parameter can be set either as an input connection or as a property value
