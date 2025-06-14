# Create Bool List

The Create Bool List node allows you to create a list of boolean values.

## Inputs

- **Items** (bool[]): A list of boolean values to include in the output list

## Outputs

- **Output** (list): The created list of boolean values

## Example

```python
# Items: [True, False, True]
# Output: [True, False, True]

# Items: [False, True]
# Output: [False, True]
```

## Notes

- All items in the input list must be boolean values
- The order of items is preserved in the output list
- The node can accept both input and property modes for the items parameter
