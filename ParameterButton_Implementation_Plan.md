# ParameterButton Implementation Plan

## Overview

This document outlines the implementation plan for adding interactive button functionality to Griptape Nodes. The plan includes `ParameterButton` for individual buttons and `ParameterButtonGroup` for grouping related buttons together.

## Core Components

### 1. ParameterButton

A UI element that displays a button and executes a specified method in the node when clicked.

#### Key Features

- **Button Text**: Display text on the button
- **Method Execution**: Execute node methods when clicked
- **Button Types**: Primary, secondary, danger, success, warning, info
- **Icons**: Support for button icons (Lucide-style)
- **Tooltips**: Help text on hover
- **States**: Disabled/enabled states
- **Layout**: Full-width option

#### Class Structure

```python
class ParameterButton(BaseNodeElement, UIOptionsMixin):
    """Represents a UI button element that can execute node methods when clicked."""
    
    # Button types
    DEFAULT_BUTTON_TYPES: ClassVar[dict[str, str]] = {
        "primary": "Primary",
        "secondary": "Secondary", 
        "danger": "Danger",
        "success": "Success",
        "warning": "Warning",
        "info": "Info",
    }
    
    # Common button icons
    DEFAULT_ICONS: ClassVar[dict[str, str]] = {
        "refresh": "refresh-cw",
        "download": "download",
        "upload": "upload",
        "delete": "trash-2",
        "edit": "edit",
        "add": "plus",
        "save": "save",
        "play": "play",
        "stop": "square",
        "pause": "pause",
        "settings": "settings",
        "help": "help-circle",
        "info": "info",
        "warning": "alert-triangle",
        "error": "alert-circle",
        "success": "check-circle",
    }
    
    type ButtonType = Literal["primary", "secondary", "danger", "success", "warning", "info"]
    
    # Properties
    _button_text: str
    _button_type: ButtonType
    _method_name: str
    _icon: str | None
    _tooltip: str | list[dict] | None
    _disabled: bool
    _full_width: bool
    _in_group: bool
    _group_position: str | None  # "first", "middle", "last", "only"
```

#### Constructor

```python
def __init__(
    self,
    button_text: str,
    method_name: str,
    *,
    button_type: ButtonType = "primary",
    icon: str | None = None,
    tooltip: str | list[dict] | None = None,
    disabled: bool = False,
    full_width: bool = False,
    ui_options: dict | None = None,
    **kwargs,
):
```

#### Convenience Methods

```python
@classmethod
def create_refresh_button(cls, method_name: str, **kwargs) -> "ParameterButton":
    """Create a refresh button with standard icon and tooltip."""

@classmethod
def create_download_button(cls, method_name: str, **kwargs) -> "ParameterButton":
    """Create a download button with standard icon and tooltip."""

@classmethod
def create_delete_button(cls, method_name: str, **kwargs) -> "ParameterButton":
    """Create a delete button with standard icon and tooltip."""

@classmethod
def create_save_button(cls, method_name: str, **kwargs) -> "ParameterButton":
    """Create a save button with standard icon and tooltip."""
```

### 2. ParameterButtonGroup

A container for grouping related buttons together with consistent styling and layout.

#### Key Features

- **Layout Options**: Horizontal, vertical, compact, stacked
- **Group Management**: Add/remove buttons dynamically
- **Position Awareness**: Buttons know their position in the group
- **Responsive Design**: Adapts to different screen sizes

#### Class Structure

```python
class ParameterButtonGroup(BaseNodeElement, UIOptionsMixin):
    """UI element for grouping related buttons together."""
    
    # Layout options
    DEFAULT_LAYOUTS: ClassVar[dict[str, str]] = {
        "horizontal": "Horizontal",
        "vertical": "Vertical",
        "compact": "Compact",
        "stacked": "Stacked",
    }
    
    type LayoutType = Literal["horizontal", "vertical", "compact", "stacked"]
    
    # Properties
    _layout: LayoutType
    _full_width: bool
```

#### Convenience Methods

```python
@classmethod
def create_crud_group(
    cls, 
    create_method: str, 
    read_method: str, 
    update_method: str, 
    delete_method: str,
    **kwargs
) -> "ParameterButtonGroup":
    """Create a standard CRUD button group."""

@classmethod
def create_file_actions_group(
    cls,
    save_method: str,
    load_method: str,
    export_method: str,
    **kwargs
) -> "ParameterButtonGroup":
    """Create a file operations button group."""

@classmethod
def create_playback_group(
    cls,
    play_method: str,
    pause_method: str,
    stop_method: str,
    **kwargs
) -> "ParameterButtonGroup":
    """Create a media playback button group."""
```

## Event System

### Button Click Event

```python
@dataclass
@PayloadRegistry.register
class ButtonClickEvent(ExecutionPayload):
    """Event fired when a ParameterButton is clicked."""
    
    element_id: str
    node_name: str
    method_name: str
```

### Node Integration

```python
class BaseNode(ABC):
    # Add to existing BaseNode class
    _button_handlers: dict[str, Callable] = field(default_factory=dict)
    
    def register_button_handler(self, method_name: str, handler: Callable) -> None:
        """Register a method to be called when a button with this method_name is clicked."""
    
    def execute_button_handler(self, method_name: str) -> Any:
        """Execute the registered button handler."""
```

## Usage Examples

### Basic Button Usage

```python
# Simple button with icon and tooltip
ParameterButton(
    button_text="Generate Image",
    method_name="generate_image",
    button_type="primary",
    icon="image",
    tooltip="Generate a new image based on current settings"
)

# Using convenience methods
ParameterButton.create_refresh_button("refresh_data")
ParameterButton.create_download_button("download_result")
ParameterButton.create_save_button("save_settings")
```

### Button Groups

```python
# Basic button group
with ParameterButtonGroup("Actions", layout="horizontal"):
    ParameterButton(
        button_text="Save",
        method_name="save_data",
        button_type="primary",
        icon="save"
    )
    ParameterButton(
        button_text="Cancel",
        method_name="cancel_operation",
        button_type="secondary",
        icon="x"
    )

# Using convenience methods
crud_group = ParameterButtonGroup.create_crud_group(
    create_method="create_item",
    read_method="read_item", 
    update_method="update_item",
    delete_method="delete_item"
)

# Vertical layout
with ParameterButtonGroup("Settings", layout="vertical", full_width=True):
    ParameterButton(
        button_text="General Settings",
        method_name="open_general_settings",
        button_type="secondary",
        icon="settings"
    )
    ParameterButton(
        button_text="Reset to Defaults",
        method_name="reset_settings",
        button_type="danger",
        icon="refresh-cw"
    )
```

### Complete Node Example

```python
class MyNode(BaseNode):
    def __init__(self, name: str):
        super().__init__(name)
        
        # Register button handlers
        self.register_button_handler("refresh_data", self.refresh_data)
        self.register_button_handler("clear_cache", self.clear_cache)
        self.register_button_handler("save_settings", self.save_settings)
        
        # Create UI elements
        with ParameterGroup("Data Management"):
            # Individual buttons
            ParameterButton(
                button_text="Refresh Data",
                method_name="refresh_data",
                button_type="primary",
                icon="refresh-cw",
                tooltip="Refresh data from source"
            )
            
            # Button group
            with ParameterButtonGroup("Actions", layout="horizontal"):
                ParameterButton(
                    button_text="Save",
                    method_name="save_settings",
                    button_type="success",
                    icon="save"
                )
                ParameterButton(
                    button_text="Clear Cache",
                    method_name="clear_cache",
                    button_type="warning",
                    icon="trash-2"
                )
    
    def refresh_data(self):
        # Implementation for refresh data
        pass
    
    def clear_cache(self):
        # Implementation for clear cache
        pass
    
    def save_settings(self):
        # Implementation for save settings
        pass
```

## Frontend Integration

### Button Rendering

- **Icon Support**: Use Lucide React or similar icon library
- **Tooltip Display**: Show tooltips on hover with support for structured content
- **Button States**: Handle disabled, loading, and normal states
- **Styling**: Apply different styles based on `button_type`

### Button Group Rendering

- **Layout Management**: Handle horizontal, vertical, compact, and stacked layouts
- **Group Styling**: Rounded corners on outer edges, shared borders
- **Responsive Design**: Adapt layout for different screen sizes
- **Focus Management**: Proper keyboard navigation within groups

### Event Handling

- **Click Events**: Emit `ButtonClickEvent` when buttons are clicked
- **Loading States**: Show loading indicators during method execution
- **Error Handling**: Display errors if method execution fails

## Implementation Steps

### Phase 1: Core Button Implementation

1. Create `ParameterButton` class in `core_types.py`
1. Add button click event system
1. Integrate with `BaseNode` for method execution
1. Add convenience methods for common button types

### Phase 2: Button Groups

1. Create `ParameterButtonGroup` class
1. Implement group management methods
1. Add convenience methods for common group patterns
1. Update `ParameterButton` to be group-aware

### Phase 3: Frontend Integration

1. Create button components
1. Implement button group layouts
1. Add event handling for button clicks
1. Implement loading and error states

### Phase 4: Testing and Documentation

1. Unit tests for button functionality
1. Integration tests for button groups
1. Documentation and examples
1. Frontend testing

## Benefits

### For Developers

- **Consistency**: Follows existing Griptape Nodes patterns
- **Flexibility**: Supports various button types and layouts
- **Ease of Use**: Convenience methods reduce boilerplate
- **Type Safety**: Proper typing for all components

### For Users

- **Visual Clarity**: Icons and tooltips improve usability
- **Organization**: Button groups organize related actions
- **Accessibility**: Proper tooltips and keyboard navigation
- **Responsive Design**: Works well on different screen sizes

### For the System

- **Event-Driven**: Integrates with existing event system
- **Extensible**: Easy to add new button types and features
- **Maintainable**: Clear separation of concerns
- **Performance**: Efficient event handling and rendering

## Files to Modify/Create

### New Files

- `src/griptape_nodes/retained_mode/events/button_events.py` - Button click events

### Modified Files

- `src/griptape_nodes/exe_types/core_types.py` - Add ParameterButton and ParameterButtonGroup classes
- `src/griptape_nodes/exe_types/node_types.py` - Add button handler methods to BaseNode
- `src/griptape_nodes/retained_mode/managers/event_manager.py` - Register button events
- Frontend components - Render buttons and handle interactions

## Conclusion

This implementation plan provides a comprehensive solution for adding interactive buttons to Griptape Nodes. The design follows existing patterns, provides flexibility for different use cases, and maintains consistency with the current architecture. The button system will enhance user experience by providing clear, organized ways to interact with node functionality.
