# Create Text List

The Create Text List node allows you to create a list of text values.

## Inputs

- **Items** (string[]): A list of text values to include in the output list

## Outputs

- **Output** (list): The created list of text values

## Example

```python
# Items: ["Hello", "World", "!"]
# Output: ["Hello", "World", "!"]

# Items: ["First", "Second", "Third"]
# Output: ["First", "Second", "Third"]
```

## Notes

- All items in the input list must be text values
- The order of items is preserved in the output list
- The node can accept both input and property modes for the items parameter
