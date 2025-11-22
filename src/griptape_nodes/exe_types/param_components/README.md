# Using ApiKeyProviderParameter Component

The `ApiKeyProviderParameter` component provides a reusable way to add API key switching functionality to nodes, allowing users to choose between using a Griptape Cloud proxy API key or their own direct API key.

## Overview

This component automatically adds:

- A toggle parameter to switch between proxy (Griptape) and user API keys
- A button on the toggle to open secrets settings (filtered to the relevant API key)
- An informational message that shows/hides based on whether the user API key is set
- Helper methods to validate and retrieve API keys

## Example: Flux Image Generation Node

The `FluxImageGeneration` node demonstrates a complete implementation. Here's how it works:

### Step 1: Import the Component

Add this import at the top of your node file:

```python
from griptape_nodes.exe_types.param_components.api_key_provider_parameter import ApiKeyProviderParameter
```

**File location:** Add this to your imports section (usually near the top with other imports)

### Step 2: Define API Key Configuration Constants

Define class-level constants for your API key information. These will be used when initializing the component:

```python
class YourNode(SuccessFailureNode):
    # API key configuration
    USER_API_KEY_NAME = "YOUR_API_KEY_NAME"  # e.g., "BFL_API_KEY", "OPENAI_API_KEY"
    USER_API_KEY_URL = "https://example.com/api/keys"  # URL where users can get their API key
    USER_API_KEY_PROVIDER_NAME = "Your Provider Name"  # e.g., "BlackForest Labs", "OpenAI"
```

**File location:** Add these as class attributes, typically near the top of your class definition (after `SERVICE_NAME` and `API_KEY_NAME` if you have them)

### Step 3: Initialize the Component in `__init__`

In your node's `__init__` method, create and initialize the component:

```python
def __init__(self, **kwargs: Any) -> None:
    super().__init__(**kwargs)
    # ... your other initialization code ...
    
    # Add API key provider component
    self._api_key_provider = ApiKeyProviderParameter(
        node=self,
        api_key_name=self.USER_API_KEY_NAME,
        provider_name=self.USER_API_KEY_PROVIDER_NAME,
        api_key_url=self.USER_API_KEY_URL,
    )
    self._api_key_provider.add_parameters()
    
    # ... rest of your initialization ...
```

**File location:** Add this code in your `__init__` method, typically after any base class initialization and before adding other parameters

### Step 4: Override `after_value_set` Method

Add this method to handle visibility updates when the API key provider toggle changes:

```python
def after_value_set(self, parameter: Parameter, value: Any) -> None:
    self._api_key_provider.after_value_set(parameter, value)
    return super().after_value_set(parameter, value)
```

**File location:** Add this method to your node class, typically near other lifecycle methods like `_process` or `_validate_api_key`

### Step 5: Use the Component in Your Processing Logic

In your `_process` method (or wherever you need to get the API key), use the component's validation method:

```python
def _process(self) -> None:
    # ... your setup code ...
    
    try:
        api_key, use_user_api = self._api_key_provider.validate_api_key()
    except ValueError as e:
        self._set_status_results(was_successful=False, result_details=str(e))
        self._handle_failure_exception(e)
        return
    
    # Use api_key and use_user_api in your API calls
    # use_user_api is True if user selected their own API key, False for proxy
    # ... rest of your processing ...
```

**File location:** Add this at the beginning of your `_process` method, before making any API calls

### Step 6: (Optional) Create a Helper Method

If you had an existing `_validate_api_key` method, you can simplify it to delegate to the component:

```python
def _validate_api_key(self) -> tuple[str, bool]:
    """Validate and return API key and whether to use user API.
    
    Returns:
        tuple: (api_key, use_user_api) where use_user_api is True if user API is enabled
    """
    return self._api_key_provider.validate_api_key()
```

**File location:** Replace your existing `_validate_api_key` method with this, or add it if you don't have one

## Complete Example

Here's a complete minimal example showing all the pieces together:

```python
from __future__ import annotations

from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.exe_types.param_components.api_key_provider_parameter import ApiKeyProviderParameter


class ExampleNode(SuccessFailureNode):
    """Example node with API key provider switching."""
    
    # API key configuration
    USER_API_KEY_NAME = "EXAMPLE_API_KEY"
    USER_API_KEY_URL = "https://example.com/api/keys"
    USER_API_KEY_PROVIDER_NAME = "Example Provider"
    
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Example node with API key switching"
        
        # Add API key provider component
        self._api_key_provider = ApiKeyProviderParameter(
            node=self,
            api_key_name=self.USER_API_KEY_NAME,
            provider_name=self.USER_API_KEY_PROVIDER_NAME,
            api_key_url=self.USER_API_KEY_URL,
        )
        self._api_key_provider.add_parameters()
        
        # Add your other parameters here
        self.add_parameter(
            Parameter(
                name="input_text",
                type="str",
                tooltip="Input text",
            )
        )
    
    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        self._api_key_provider.after_value_set(parameter, value)
        return super().after_value_set(parameter, value)
    
    def _process(self) -> None:
        # Get API key and determine which API to use
        try:
            api_key, use_user_api = self._api_key_provider.validate_api_key()
        except ValueError as e:
            self._set_status_results(was_successful=False, result_details=str(e))
            self._handle_failure_exception(e)
            return
        
        # Use api_key and use_user_api in your API logic
        input_text = self.get_parameter_value("input_text")
        
        if use_user_api:
            # Use direct API with user's key
            result = self._call_user_api(api_key, input_text)
        else:
            # Use proxy API with Griptape Cloud key
            result = self._call_proxy_api(api_key, input_text)
        
        # Process result...
        self._set_status_results(was_successful=True, result_details="Success")
    
    def _call_user_api(self, api_key: str, input_text: str) -> dict:
        # Your direct API call logic here
        pass
    
    def _call_proxy_api(self, api_key: str, input_text: str) -> dict:
        # Your proxy API call logic here
        pass
```

## Component API Reference

### Initialization Parameters

When creating an `ApiKeyProviderParameter` instance, you must provide:

- **`node`** (BaseNode): The node instance to add parameters to
- **`api_key_name`** (str): The name of the user's API key secret (e.g., `"BFL_API_KEY"`)
- **`provider_name`** (str): The display name of the API provider (e.g., `"BlackForest Labs"`)
- **`api_key_url`** (str): The URL where users can obtain their API key

Optional parameters:

- **`parameter_name`** (str, default: `"api_key_provider"`): Name for the toggle parameter
- **`proxy_api_key_name`** (str, default: `"GT_CLOUD_API_KEY"`): Name of the proxy API key secret
- **`on_label`** (str, default: `"Customer"`): Label when user API is enabled
- **`off_label`** (str, default: `"Griptape"`): Label when proxy API is enabled

### Available Methods

#### `add_parameters()`

Adds the toggle parameter and message to the node. Call this once in `__init__`.

#### `after_value_set(parameter: Parameter, value: Any)`

Handles visibility updates when the toggle changes. Call this from your node's `after_value_set` method.

#### `validate_api_key() -> tuple[str, bool]`

Validates and returns the API key and whether to use user API. Returns `(api_key, use_user_api)`.

**Raises:** `ValueError` if the required API key is not set.

#### `is_user_api_enabled() -> bool`

Checks if user API is currently enabled.

#### `get_api_key(use_user_api: bool) -> str`

Gets the API key for the specified mode.

**Raises:** `ValueError` if the API key is not set.

#### `check_api_key_set(api_key: str) -> bool`

Checks if an API key exists and is not empty.

## Migration Guide: Converting Existing Nodes

If you have an existing node that manually handles API key switching, here's how to migrate:

### Before (Manual Implementation)

```python
def __init__(self, **kwargs: Any) -> None:
    super().__init__(**kwargs)
    
    # Manual toggle parameter
    self.add_parameter(
        ParameterBool(
            name="api_key_provider",
            default_value=False,
            # ... lots of configuration ...
        )
    )
    
    # Manual message
    self.add_node_element(
        ParameterMessage(
            name="set_api_key",
            # ... lots of configuration ...
        )
    )

def after_value_set(self, parameter: Parameter, value: Any) -> None:
    if parameter.name == "api_key_provider":
        # Manual visibility logic
        if value:
            if not self.check_api_key_set(self.USER_API_KEY_NAME):
                self.show_message_by_name("set_api_key")
        else:
            self.hide_message_by_name("set_api_key")
    return super().after_value_set(parameter, value)

def _validate_api_key(self) -> tuple[str, bool]:
    use_user_api = self.get_parameter_value("api_key_provider") or False
    api_key_name = "USER_KEY" if use_user_api else "GT_CLOUD_API_KEY"
    api_key = GriptapeNodes.SecretsManager().get_secret(api_key_name)
    # ... validation logic ...
    return api_key, use_user_api
```

### After (Using Component)

```python
from griptape_nodes.exe_types.param_components.api_key_provider_parameter import ApiKeyProviderParameter

def __init__(self, **kwargs: Any) -> None:
    super().__init__(**kwargs)
    
    # Component handles everything
    self._api_key_provider = ApiKeyProviderParameter(
        node=self,
        api_key_name=self.USER_API_KEY_NAME,
        provider_name=self.USER_API_KEY_PROVIDER_NAME,
        api_key_url=self.USER_API_KEY_URL,
    )
    self._api_key_provider.add_parameters()

def after_value_set(self, parameter: Parameter, value: Any) -> None:
    self._api_key_provider.after_value_set(parameter, value)
    return super().after_value_set(parameter, value)

def _validate_api_key(self) -> tuple[str, bool]:
    return self._api_key_provider.validate_api_key()
```

## Common Patterns

### Pattern 1: Simple API Switching

If your node just needs to switch between two API endpoints with different keys:

```python
api_key, use_user_api = self._api_key_provider.validate_api_key()

if use_user_api:
    base_url = "https://api.provider.com/v1"
    headers = {"Authorization": f"Bearer {api_key}"}
else:
    base_url = self._proxy_base
    headers = {"Authorization": f"Bearer {api_key}"}
```

### Pattern 2: Different API Configurations

If your proxy and user APIs have different configurations (like in Flux Image Generation):

```python
api_key, use_user_api = self._api_key_provider.validate_api_key()

config_mode = "user" if use_user_api else "proxy"
config = YOUR_API_CONFIG[config_mode]

# Use config for URL, headers, etc.
url = config["url_template"].format(base=config["base_url"])
headers = config["headers"](api_key)
```

### Pattern 3: Conditional Logic Based on API Type

```python
api_key, use_user_api = self._api_key_provider.validate_api_key()

if use_user_api:
    # User API specific logic
    result = await self._call_user_api(api_key, params)
else:
    # Proxy API specific logic
    result = await self._call_proxy_api(api_key, params)
```

## Troubleshooting

### Message Not Showing/Hiding

**Problem:** The message doesn't appear when the toggle is switched.

**Solution:** Make sure you're calling `self._api_key_provider.after_value_set(parameter, value)` in your node's `after_value_set` method and that it's called before `super().after_value_set()`.

### API Key Not Found Error

**Problem:** Getting `ValueError` about missing API key even though it's set.

**Solution:**

1. Verify the API key name matches exactly (case-sensitive)
1. Check that the secret is set in Settings → Secrets
1. Ensure you're using the correct `api_key_name` when initializing the component

### Toggle Not Appearing

**Problem:** The API key provider toggle doesn't appear in the UI.

**Solution:** Make sure you're calling `self._api_key_provider.add_parameters()` in your `__init__` method.

## See Also

- [Flux Image Generation Node](../../libraries/griptape_nodes_library/griptape_nodes_library/image/flux_image_generation.py) - Complete working example
- [ApiKeyProviderParameter Component](../../src/griptape_nodes/exe_types/param_components/api_key_provider_parameter.py) - Component source code
