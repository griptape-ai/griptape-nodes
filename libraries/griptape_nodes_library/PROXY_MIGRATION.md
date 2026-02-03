# Proxy Node Migration Guide

This document describes the migration of proxy nodes from V1 synchronous proxy API to V2 async proxy API with the `BaseProxyNode` base class.

## Migration Overview

The migration involves two main steps:

1. **V1 → V2 Proxy API Migration**: Update nodes to use the async V2 proxy endpoints
1. **BaseProxyNode Integration**: Refactor to use the common `BaseProxyNode` base class

## V2 Proxy API Changes

### V1 (Synchronous)

```
POST /api/proxy/models/{model_id}
  → Returns complete response immediately
```

### V2 (Asynchronous)

```
1. POST /api/proxy/v2/models/{model_id}
   → Returns generation_id

2. Poll: GET /api/proxy/v2/generations/{generation_id}
   → Returns status (PENDING, IN_PROGRESS, COMPLETED, FAILED, ERRORED)

3. When COMPLETED: GET /api/proxy/v2/generations/{generation_id}/result
   → Returns same response format as V1 would have returned
```

## BaseProxyNode Benefits

The `BaseProxyNode` class provides:

1. **Unified async polling logic**: No need to implement polling in each node
1. **Consistent error handling**: Standard error extraction hierarchy
1. **Common generation workflow**: Submit → Poll → Fetch Result → Parse
1. **Reduced boilerplate**: ~100-150 lines removed per node

## Migration Steps

### Step 1: Update Imports

```python
# Remove
from griptape_nodes.exe_types.node_types import SuccessFailureNode
import os
from urllib.parse import urljoin
from time import time

# Add
from griptape_nodes_library.base_proxy_node import BaseProxyNode
import httpx  # if not already imported
```

### Step 2: Change Base Class

```python
# Before
class MyNode(SuccessFailureNode):
    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/")

# After
class MyNode(BaseProxyNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # No proxy URL setup needed - handled by BaseProxyNode
```

### Step 3: Implement Required Methods

```python
def _get_api_model_id(self) -> str:
    """Return the model ID for API calls."""
    return self.get_parameter_value("model") or "default-model-id"

async def _build_payload(self) -> dict[str, Any]:
    """Build the request payload (without model field)."""
    return {
        "prompt": self.get_parameter_value("prompt"),
        # ... other parameters
    }

async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
    """Parse the result and set output parameters."""
    # Extract data from result_json
    # Set self.parameter_output_values[...]
    # Call self._set_status_results(was_successful=True/False, ...)

def _set_safe_defaults(self) -> None:
    """Clear output parameters on error."""
    self.parameter_output_values["generation_id"] = ""
    self.parameter_output_values["result"] = None
```

### Step 4: Use generation_id in Filenames

```python
# Before
filename = f"my_node_{int(time.time())}.jpg"

# After
filename = f"my_node_{generation_id}.jpg"
```

### Step 5: Error Extraction (Optional Override)

The base class provides a default implementation with this hierarchy:

1. `status_detail.details` (user-oriented message)
1. `status_detail` object
1. `error` field
1. Full response

Override only if you have provider-specific error patterns:

```python
def _extract_error_message(self, response_json: dict[str, Any]) -> str:
    """Extract error message from failed generation."""
    # Try provider-specific patterns first
    parsed_provider = self._parse_provider_response(response_json.get("provider_response"))
    if parsed_provider and parsed_provider.get("error"):
        # ... custom logic
        pass

    # Fall back to base implementation
    return super()._extract_error_message(response_json)
```

## Migration Status

### ✅ Completed Migrations (V2 + GriptapeProxyNode)

**Audio Generation:**

- `eleven_labs_text_to_speech.py`
- `eleven_labs_music_generation.py`
- `eleven_labs_sound_effect.py`

**Image Generation:**

- `flux_2_image_generation.py`
- `seedream_image_generation.py`

**Video Generation (Kling):**

- `kling_text_to_video_generation.py`
- `kling_image_to_video_generation.py`
- `kling_motion_control.py`
- `kling_omni_video_generation.py`
- `kling_video_extension.py`

**Video Generation (Seedance):**

- `seedance_video_generation.py`

### ⏳ Pending Migration (Still on V1)

**Image Generation:**

- `google_image_generation.py`
- `qwen_image_generation.py`
- `qwen_image_edit.py`
- `flux_image_generation.py` ⚠️ *Blocked: Has user API key feature, waiting for proxy support*

**Video Generation:**

- `veo3_video_generation.py`
- `sora_video_generation.py`
- `wan_text_to_video_generation.py`
- `wan_image_to_video_generation.py`
- `wan_animate_generation.py`
- `omnihuman_video_generation.py`
- `omnihuman_subject_recognition.py`
- `omnihuman_subject_detection.py`

**Image Upscaling:**

- `seedvr_image_upscale.py`

**Video Upscaling:**

- `seedvr_video_upscale.py`

## Common Patterns

### Handling SeedParameter

```python
async def _build_payload(self) -> dict[str, Any]:
    # Preprocess seed first
    self._seed_parameter.preprocess()

    return {
        "seed": self._seed_parameter.get_seed(),
        # ... other params
    }
```

### Handling PublicArtifactUrlParameter (Cleanup)

```python
async def aprocess(self) -> None:
    """Override to add cleanup."""
    try:
        await super().aprocess()
    finally:
        self._public_artifact_url_parameter.delete_uploaded_artifact()
```

### Multiple Output Images

```python
async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
    images = result_json.get("images", [])

    for idx, image_data in enumerate(images):
        url = image_data.get("url")
        artifact = await self._save_single_image(url, generation_id, idx)
        # Store in appropriate output parameter
```

### Downloading and Saving Media

```python
# Download using httpx (async)
async def _download_bytes_from_url(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=120)
            resp.raise_for_status()
            return resp.content
    except Exception:
        return None

# Save with generation_id
filename = f"node_name_{generation_id}.{extension}"
static_files_manager = GriptapeNodes.StaticFilesManager()
saved_url = static_files_manager.save_static_file(bytes_data, filename)
```

## Key Improvements

### Before Migration (V1)

- ❌ Manual polling implementation (~50-100 lines per node)
- ❌ Inconsistent error handling
- ❌ Timestamp-based filenames (collisions possible)
- ❌ Synchronous HTTP requests (requests library)
- ❌ Duplicated validation and submission logic

### After Migration (V2 + BaseProxyNode)

- ✅ Automatic async polling handled by base class
- ✅ Consistent error extraction hierarchy
- ✅ Generation ID-based filenames (better traceability)
- ✅ Async HTTP requests (httpx library)
- ✅ Minimal boilerplate - just implement 3-4 methods

## Error Message Hierarchy

The base class implements this error extraction hierarchy:

1. **`status_detail.details`**: User-oriented message from the provider

    - Example: `"Input data may contain inappropriate content..."`

1. **`status_detail` object**: Full error details if no details field

    - Example: `{"error": "invalid input", "details": "..."}`

1. **`error` field**: Top-level error message

    - Example: `"Model request failed"`

1. **Full response**: Last resort, show everything

    - For debugging unknown error formats

Nodes can override `_extract_error_message()` to add provider-specific patterns before falling back to the base implementation.

## Testing Checklist

After migrating a node:

- [ ] Run `make check` - all linting and type checks pass
- [ ] Test successful generation
- [ ] Test error cases (invalid input, API errors)
- [ ] Verify generation_id is used in filenames
- [ ] Verify error messages are user-friendly
- [ ] Check cleanup (e.g., PublicArtifactUrlParameter deletion)
- [ ] Confirm async/await throughout

## Important Implementation Details

### What BaseProxyNode Handles Automatically

You **DO NOT** need to implement these - they're handled by the base class:

1. **API Key Validation**: `_validate_api_key()` - automatically checks `GT_CLOUD_API_KEY`
1. **Request Submission**: `_submit_generation()` - POSTs to `/api/proxy/v2/models/{model_id}`
1. **Status Polling**: `_poll_generation_status()` - polls until COMPLETED/FAILED/ERRORED
1. **Result Fetching**: Automatically fetches from `/api/proxy/v2/generations/{generation_id}/result`
1. **Output Parameters**: Automatically sets `generation_id` and `provider_response` output parameters
1. **Error Handling**: Calls `_extract_error_message()` on FAILED/ERRORED statuses
1. **Model ID**: Automatically adds model field to payload using `_get_api_model_id()`
1. **Execution Flow**: Implements `aprocess()` to orchestrate the entire workflow

### Polling Configuration

BaseProxyNode uses these defaults (not configurable per-node):

- **Poll Interval**: 2 seconds
- **Timeout**: 600 seconds (10 minutes)
- **Status Check**: Polls `/api/proxy/v2/generations/{generation_id}` until terminal status

### Process Method Changes

```python
# V1 Pattern (synchronous or AsyncResult)
def process(self) -> AsyncResult[None]:
    yield lambda: self._process()

def _process(self) -> None:
    # ... manual polling logic ...

# V2 Pattern (async only)
async def aprocess(self) -> None:
    """Override only if you need custom pre/post processing."""
    # Pre-processing (optional)
    try:
        await super().aprocess()  # Calls the base class workflow
    finally:
        # Cleanup (optional)
        pass
```

Most nodes don't need to override `aprocess()` at all - the base class handles everything.

### Output Parameters

The following output parameters are **automatically set** by BaseProxyNode:

```python
# Automatically set - DO NOT set these in your node
self.parameter_output_values["generation_id"] = generation_id  # Set after submission
self.parameter_output_values["provider_response"] = status_response  # Set during polling
```

Your node should only set domain-specific outputs (images, audio, video, etc.).

### Payload Construction

**CRITICAL**: Do NOT include the `model` field in your payload:

```python
# ❌ WRONG - includes model
async def _build_payload(self) -> dict[str, Any]:
    return {
        "model": "my-model-id",  # DON'T DO THIS
        "prompt": "...",
    }

# ✅ CORRECT - model is handled separately
def _get_api_model_id(self) -> str:
    return "my-model-id"

async def _build_payload(self) -> dict[str, Any]:
    return {
        "prompt": "...",  # Just the parameters
    }
```

BaseProxyNode automatically adds the model field to the request.

### Validation Patterns

Use `validate_before_node_run()` for pre-execution validation:

```python
def validate_before_node_run(self) -> list[Exception] | None:
    exceptions = super().validate_before_node_run() or []

    # Validate required parameters
    if not self.get_parameter_value("prompt"):
        exceptions.append(ValueError(f"{self.name} requires a prompt"))

    # Validate parameter constraints
    images = self.get_parameter_value("images") or []
    if len(images) > 10:
        exceptions.append(ValueError(f"{self.name} allows max 10 images, got {len(images)}"))

    return exceptions if exceptions else None
```

This prevents execution if validation fails, saving API calls.

## Real Error Response Examples

### Example 1: Qwen Inappropriate Content

**Raw V2 Response:**

```json
{
  "generation_id": "bd190698-ebd9-4171-986d-cd6edaf5cdf7",
  "model_id": "qwen-image-plus",
  "status": "FAILED",
  "created_at": "2025-12-22T22:00:01.220580+00:00",
  "updated_at": "2025-12-22T22:00:13.025941+00:00",
  "status_detail": {
    "error": "invalid input",
    "details": "Input data may contain inappropriate content. For details, see: https://www.alibabacloud.com/help/en/model-studio/error-code#inappropriate-content"
  }
}
```

**User-Facing Error Message (after extraction):**

```
MyNode Input data may contain inappropriate content. For details, see: https://www.alibabacloud.com/help/en/model-studio/error-code#inappropriate-content
```

The base class extracts `status_detail.details` as the primary user message.

### Example 2: Provider-Specific Error (Legacy Pattern)

Some providers return errors in `provider_response`:

```json
{
  "generation_id": "...",
  "status": "FAILED",
  "provider_response": "{\"error\": {\"message\": \"Rate limit exceeded\", \"code\": \"429\", \"type\": \"rate_limit_error\"}}"
}
```

Nodes with provider-specific patterns override `_extract_error_message()`:

```python
def _extract_error_message(self, response_json: dict[str, Any]) -> str:
    # Try provider-specific pattern
    parsed = self._parse_provider_response(response_json.get("provider_response"))
    if parsed and parsed.get("error"):
        error = parsed["error"]
        if isinstance(error, dict):
            return f"{self.name} {error.get('message', error)}"

    # Fall back to standard extraction
    return super()._extract_error_message(response_json)
```

### Example 3: Top-Level Error

```json
{
  "generation_id": "...",
  "status": "ERRORED",
  "error": "Model is temporarily unavailable"
}
```

Base class extracts: `"MyNode Model is temporarily unavailable"`

## Common Gotchas and Pitfalls

### 1. Forgetting to Use generation_id Parameter

```python
# ❌ WRONG - ignores generation_id
async def _parse_result(self, result_json: dict[str, Any], _generation_id: str) -> None:
    filename = f"image_{int(time.time())}.jpg"  # Uses timestamp

# ✅ CORRECT - uses generation_id
async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
    filename = f"image_{generation_id}.jpg"
```

### 2. Setting generation_id or provider_response Manually

```python
# ❌ WRONG - these are set automatically
async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
    self.parameter_output_values["generation_id"] = generation_id  # DON'T DO THIS
    self.parameter_output_values["provider_response"] = result_json  # DON'T DO THIS

# ✅ CORRECT - only set domain-specific outputs
async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
    self.parameter_output_values["image"] = image_artifact
```

### 3. Including Model in Payload

```python
# ❌ WRONG - model handled separately
async def _build_payload(self) -> dict[str, Any]:
    return {"model": self.get_parameter_value("model"), "prompt": "..."}

# ✅ CORRECT - model in separate method
def _get_api_model_id(self) -> str:
    return self.get_parameter_value("model")

async def _build_payload(self) -> dict[str, Any]:
    return {"prompt": "..."}
```

### 4. Not Handling Async Properly

```python
# ❌ WRONG - synchronous download
def _download_image(self, url: str) -> bytes:
    import requests
    return requests.get(url).content

# ✅ CORRECT - async download
async def _download_image(self, url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=120)
        resp.raise_for_status()
        return resp.content
```

### 5. Forgetting to Call super() in \_extract_error_message()

```python
# ❌ WRONG - doesn't fall back to base implementation
def _extract_error_message(self, response_json: dict[str, Any]) -> str:
    error = response_json.get("error")
    if error:
        return str(error)
    return "Unknown error"  # Misses status_detail.details!

# ✅ CORRECT - falls back to base implementation
def _extract_error_message(self, response_json: dict[str, Any]) -> str:
    # Try provider-specific patterns
    if response_json.get("provider_response"):
        # ... custom logic
        pass

    # Fall back to standard hierarchy
    return super()._extract_error_message(response_json)
```

## What Gets Removed During Migration

Delete these entirely - they're handled by BaseProxyNode:

```python
# ❌ DELETE - No longer needed
SERVICE_NAME = "Griptape"
API_KEY_NAME = "GT_CLOUD_API_KEY"

def __init__(self, **kwargs):
    # DELETE proxy URL setup
    base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
    base_slash = base if base.endswith("/") else base + "/"
    api_base = urljoin(base_slash, "api/")
    self._proxy_base = urljoin(api_base, "proxy/")

# DELETE entire methods
def _validate_api_key(self) -> str:
    api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
    if not api_key:
        raise ValueError(f"{self.name} is missing {self.API_KEY_NAME}")
    return api_key

def _submit_request(self, params, headers) -> str:
    # ... 50+ lines of POST logic and error handling ...

def _poll_for_result(self, generation_id, headers) -> None:
    # ... 50-100 lines of polling logic ...
```

## Provider Response Patterns

### Standard V2 Response

The result from `/api/proxy/v2/generations/{generation_id}/result` contains the **exact same response** the provider would have returned:

```python
# Example: Image generation result
result_json = {
    "url": "https://provider.com/image.jpg",
    "width": 1024,
    "height": 1024,
    # ... provider-specific fields
}
```

Your `_parse_result()` method receives this directly.

### Legacy provider_response Field

Some V1 nodes parsed `provider_response` for errors. This pattern is still supported:

```python
# V2 status response during polling
{
    "status": "FAILED",
    "provider_response": "{...}"  # JSON string or dict
}
```

Helper methods for legacy pattern:

```python
def _parse_provider_response(self, provider_response: Any) -> dict[str, Any] | None:
    """Parse provider_response if it's a JSON string."""
    if isinstance(provider_response, str):
        try:
            return json.loads(provider_response)
        except Exception:
            return None
    if isinstance(provider_response, dict):
        return provider_response
    return None

def _format_provider_error(
    self, parsed_provider_response: dict[str, Any] | None, top_level_error: Any
) -> str | None:
    """Format error message from parsed provider response."""
    if not parsed_provider_response:
        return None

    provider_error = parsed_provider_response.get("error")
    if not provider_error:
        return None

    if isinstance(provider_error, dict):
        error_message = provider_error.get("message", "")
        details = f"{error_message}"
        if error_code := provider_error.get("code"):
            details += f"\nError Code: {error_code}"
        if error_type := provider_error.get("type"):
            details += f"\nError Type: {error_type}"
        if top_level_error:
            details = f"{top_level_error}\n\n{details}"
        return details

    return None
```

Only implement these if your provider uses the legacy `provider_response` pattern.

## Conditional Parameters (Mode-Based)

Some nodes show/hide parameters based on selections:

```python
def after_value_set(self, parameter: Parameter, value: Any) -> None:
    super().after_value_set(parameter, value)

    if parameter.name == "upscale_mode":
        if value == "factor":
            self.hide_parameter_by_name("target_resolution")
            self.show_parameter_by_name("upscale_factor")
        elif value == "target":
            self.show_parameter_by_name("target_resolution")
            self.hide_parameter_by_name("upscale_factor")
```

Handle conditional parameters in `_build_payload()`:

```python
async def _build_payload(self) -> dict[str, Any]:
    upscale_mode = self.get_parameter_value("upscale_mode")
    payload = {"upscale_mode": upscale_mode}

    # Add mode-specific parameters
    if upscale_mode == "factor":
        payload["upscale_factor"] = self.get_parameter_value("upscale_factor")
    elif upscale_mode == "target":
        payload["target_resolution"] = self.get_parameter_value("target_resolution")

    return payload
```

## Notes

- The V2 proxy generalizes provider interactions - all providers follow the same async pattern
- BaseProxyNode handles API key validation, polling, and status checking automatically
- Terminal statuses: `COMPLETED`, `FAILED`, `ERRORED`
- `generation_id` provides better entropy than timestamps for unique filenames
- The `provider_response` field may contain provider-specific error details (legacy pattern)
- Result from `/result` endpoint is exactly what the provider returned (no wrapper)
- BaseProxyNode polls every 2 seconds with a 10-minute timeout
- All HTTP requests use `httpx` (async) instead of `requests` (sync)
