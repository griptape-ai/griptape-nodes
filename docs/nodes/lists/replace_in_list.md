# Replace In List

The Replace In List node allows you to replace an item in a list either by matching the item or by its index.

## Inputs

- **Items** (list): The list to modify
- **Item To Replace** (any): The item to replace in the list (shown when Replace By is "item")
- **Index To Replace** (int): The index of the item to replace (shown when Replace By is "index")
- **New Item** (any): The new item to replace with

## Properties

- **Replace By** (str): How to identify the item to replace
    - Options:
        - "item": Replace by matching the item value
        - "index": Replace by index position

## Outputs

- **Output** (list): The modified list with the item replaced

## Example

```python
# Input list: [1, 2, 3, 4]

# Replace by item:
# Item To Replace: 3
# New Item: "three"
# Output: [1, 2, "three", 4]

# Replace by index:
# Index To Replace: 1
# New Item: "two"
# Output: [1, "two", 3, 4]
```

## Notes

- When replacing by item, the first occurrence of the item will be replaced
- When replacing by index, the index must be within the bounds of the list
- If the item is not found when replacing by item, no changes will be made
- The original list is not modified; a new list is returned
