# Split List

The Split List node allows you to split a list into two parts either by index or by matching an item value.

## Inputs

- **Items** (list): The list to split
- **Split Index** (int): The index to split the list at (shown when Split By is "index")
- **Split Item** (any): The item to split the list at (shown when Split By is "item")

## Properties

- **Split By** (str): How to split the list
    - Options:
        - "index": Split at a specific index position
        - "item": Split at a specific item value
- **Keep Split Item** (bool): Whether to keep the split item in the second list (shown when Split By is "item")

## Outputs

- **Output A** (list): The first part of the split list
- **Output B** (list): The second part of the split list

## Example

```python
# Input list: [1, 2, 3, 4]

# Split by index:
# Split Index: 2
# Output A: [1, 2]
# Output B: [3, 4]

# Split by item:
# Split Item: 3
# Keep Split Item: True
# Output A: [1, 2]
# Output B: [3, 4]

# Split by item:
# Split Item: 3
# Keep Split Item: False
# Output A: [1, 2]
# Output B: [4]
```

## Notes

- When splitting by index, the index is included in the second list
- When splitting by item, you can choose whether to keep the split item in the second list
- If the item is not found when splitting by item, no split will occur
- The index must be within the bounds of the list when splitting by index
- The original list is not modified; new lists are returned
