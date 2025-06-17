# Create Float List

The Create Float List node allows you to create a list of float values.

## Inputs

- **Items** (float[]): A list of float values to include in the output list

## Outputs

- **Output** (list): The created list of float values

## Example

```python
# Items: [1.5, 2.7, 3.14]
# Output: [1.5, 2.7, 3.14]

# Items: [-0.5, 0.0, 42.0]
# Output: [-0.5, 0.0, 42.0]
```

## Notes

- All items in the input list must be float values
- The order of items is preserved in the output list
- The node can accept both input and property modes for the items parameter
