# Select From List

Select an item from a list of strings with a dropdown interface.

## Description

The Select From List node allows users to choose a single item from a list of strings using a dropdown interface. It automatically updates its choices when the input list changes and preserves the current selection when possible.

## Parameters

### Input Parameters

| Parameter | Type | Description                    | Default |
| --------- | ---- | ------------------------------ | ------- |
| `list`    | list | List of items to select from  | `[]`    |

### Output Parameters

| Parameter      | Type   | Description                        |
| -------------- | ------ | ---------------------------------- |
| `selected_item` | string | The currently selected item        |

## Features

- **Dynamic Dropdown**: Automatically populates dropdown with items from the input list
- **Selection Preservation**: Maintains current selection when list updates (if item still exists)
- **String Conversion**: Converts all list items to strings for consistent comparison
- **Real-time Updates**: Updates immediately when input list changes
- **Safe Handling**: Gracefully handles empty or invalid lists

## Examples

### Basic List Selection

```python
# Input list: ["Apple", "Banana", "Cherry", "Date"]
# User selects: "Banana"
# Output: "Banana"
```

### Status Selection

```python
# Input list: ["In Progress", "Not Started", "Waiting", "Completed", "Blocked"]
# User selects: "Completed"
# Output: "Completed"
```

### Dynamic List Updates

```python
# Initial list: ["Option A", "Option B", "Option C"]
# User selects: "Option B"
# List updates to: ["Option A", "Option B", "Option D", "Option E"]
# Selection preserved: "Option B" (still exists in new list)

# If list updates to: ["Option X", "Option Y", "Option Z"]
# Selection resets to: "Option X" (first item in new list)
```

## Use Cases

- **Status Selection**: Choose from predefined status values (e.g., "In Progress", "Completed")
- **Category Selection**: Select from a list of categories or types
- **Configuration Choices**: Pick from available configuration options
- **User Interface**: Provide dropdown selection in workflows
- **Data Filtering**: Select specific items from generated lists

## Workflow Examples

### Status Management Workflow

```
Create Text List → Select From List → Process Selected Status
     ↓                    ↓
["In Progress",      "Completed"    → Update task status
 "Not Started", 
 "Waiting", 
 "Completed", 
 "Blocked"]
```

### Dynamic Option Selection

```
API Response → Extract Options → Select From List → Use Selection
     ↓              ↓                ↓
JSON data    → ["Option 1",    → "Option 2"    → Process choice
              "Option 2", 
              "Option 3"]
```

## Behavior

### Selection Logic

1. **Initial Load**: Selects the first item in the list
2. **List Update**: 
   - If current selection exists in new list → keeps current selection
   - If current selection doesn't exist → selects first item in new list
3. **Empty List**: Clears selection (empty string)
4. **Invalid Input**: Clears selection (empty string)

### String Conversion

All list items are automatically converted to strings for consistent comparison:
- Numbers: `123` → `"123"`
- Booleans: `True` → `"True"`
- Objects: `{"key": "value"}` → `"{'key': 'value'}"`

## Related Nodes

- [Create Text List](create_text_list.md) - Generate a list of text items
- [Create List](create_list.md) - Create lists from various inputs
- [Get From List](get_from_list.md) - Get item by index from list
- [Get Index Of Item](get_index_of_item.md) - Find index of specific item
- [Display List](display_list.md) - Display list contents
