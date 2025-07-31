# Griptape Nodes Iframe SDK

A simple SDK for creating iframe components that communicate with the parent window. This SDK abstracts away all the boilerplate code needed for iframe communication, loading states, and value synchronization.

## Features

- **Automatic message handling** - Handles communication with parent window
- **Loading states** - Built-in loading spinner and state management
- **Value synchronization** - Automatic two-way value updates
- **Error handling** - Built-in error handling and status updates
- **UI utilities** - Common UI patterns and styles
- **Simple API** - Easy to use with minimal boilerplate

## Quick Start

### 1. Include the SDK

```html
<script src="iframe-sdk.js"></script>
```

### 2. Create a component

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Component</title>
    <style>
        /* Include common styles */
        .loading { /* ... */ }
        .status { /* ... */ }
        .hidden { display: none; }
        
        /* Your custom styles */
        .my-input {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Loading state -->
        <div id="loadingState" class="loading">
            <div class="loading-spinner"></div>
            <div>Waiting for parent value...</div>
        </div>
        
        <!-- Main content -->
        <div id="mainContent" class="hidden">
            <input 
                type="text" 
                id="myInput" 
                class="my-input"
                placeholder="Enter value..."
                onchange="updateValue()"
            >
            
            <div class="status" id="status">
                <strong>Status:</strong> <span id="statusText">Ready</span>
            </div>
        </div>
    </div>

    <script src="iframe-sdk.js"></script>
    <script>
        // Create component instance
        const component = new IframeComponent({
            componentName: 'My Component',
            defaultValue: '',
            onValueChange: (value) => {
                // Called when we receive a value from parent
                UIUtils.showMainContent();
                
                const input = document.getElementById('myInput');
                if (input) input.value = value || '';
                
                UIUtils.updateStatus(`Received: ${value}`);
            },
            onError: (error) => {
                UIUtils.updateStatus(`Error: ${error}`);
            }
        });
        
        // Update value from input
        function updateValue() {
            const input = document.getElementById('myInput');
            const value = input.value;
            
            component.updateValue(value);
            UIUtils.updateStatus(`Sent: ${value}`);
        }
    </script>
</body>
</html>
```

## API Reference

### IframeComponent

The main class for creating iframe components.

#### Constructor Options

```javascript
const component = new IframeComponent({
    componentName: 'My Component',     // Name for logging
    defaultValue: '',                  // Default value when parent sends null/undefined
    onValueChange: (value) => {},     // Called when value changes from parent
    onReady: () => {},                // Called when component is ready
    onError: (error) => {}            // Called when errors occur
});
```

#### Methods

- `updateValue(value)` - Send a value update to the parent
- `getValue()` - Get the current value
- `hasInitialValue()` - Check if we've received initial value from parent

### UIUtils

Utility functions for common UI patterns.

#### Methods

- `showLoading()` - Show loading state
- `showMainContent()` - Show main content and hide loading
- `updateStatus(message)` - Update status display
- `createLoadingSpinner()` - Get loading spinner HTML
- `createStatusDisplay()` - Get status display HTML

### CommonStyles

CSS string with common styles for loading, status, and layout.

## Examples

### Simple Text Input

See `SimpleTextInputWithSDK.html` for a complete example of a text input component.

### Color Picker

See `ColorPickerWithSDK.html` for a more complex example with validation and multiple inputs.

## Message Protocol

The SDK handles these message types automatically:

### From Parent to Iframe

```javascript
{
    type: 'SET_VALUE',
    value: 'some value'
}
```

### From Iframe to Parent

```javascript
{
    type: 'VALUE_UPDATE',
    value: 'new value'
}
```

```javascript
{
    type: 'IFRAME_READY',
    message: 'Component is ready'
}
```

## Migration from Manual Implementation

If you have existing components, here's how to migrate:

### Before (Manual)

```javascript
let currentValue = '';
let hasReceivedInitialValue = false;
let isReceivingFromParent = false;

function handleParentMessage(event) {
    const { type, value } = event.data;
    if (type === 'SET_VALUE') {
        isReceivingFromParent = true;
        currentValue = value;
        // Update UI...
        isReceivingFromParent = false;
    }
}

function sendValueUpdate(value) {
    if (isReceivingFromParent) return;
    window.parent.postMessage({
        type: 'VALUE_UPDATE',
        value: value
    }, '*');
}

window.addEventListener('message', handleParentMessage);
setTimeout(() => {
    window.parent.postMessage({
        type: 'IFRAME_READY',
        message: 'Ready'
    }, '*');
}, 100);
```

### After (With SDK)

```javascript
const component = new IframeComponent({
    componentName: 'My Component',
    onValueChange: (value) => {
        // Update UI with value
    }
});

function updateValue() {
    component.updateValue(newValue);
}
```

## Best Practices

1. **Always include loading states** - Use the provided loading spinner
1. **Handle errors gracefully** - Use the `onError` callback
1. **Validate inputs** - Add validation before sending values
1. **Use descriptive component names** - Helps with debugging
1. **Keep components focused** - One component per file
1. **Test communication** - Verify parent-iframe communication works

## Browser Support

The SDK works in all modern browsers that support:

- ES6 classes
- `window.postMessage`
- `addEventListener`
- `setTimeout`

## Troubleshooting

### Common Issues

1. **Messages not received** - Check that the SDK is loaded before creating the component
1. **Values not updating** - Ensure you call `component.updateValue()` when user changes input
1. **Loading state stuck** - Verify `UIUtils.showMainContent()` is called in `onValueChange`
1. **Parent communication fails** - Check browser console for error messages

### Debug Tips

- Use browser dev tools to inspect iframe messages
- Check console logs for SDK messages
- Verify parent window is sending correct message format
- Test with simple values first, then complex data
