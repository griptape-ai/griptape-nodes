# How to Debug Your Workflow Using the Bootstrapping Script

## Overview

This bootstrapping script allows you to run and debug your workflow directly in your code editor, without launching the UI. This guide explains how to implement it in your workflow files.

## What You'll Need

- Your workflow scene file (e.g., `workflow.py`)
- A code editor like VS Code
- The path to your node library (found in your configuration editor)
- The name of your workflow "flow"

## Setup Steps

### 1. Add the bootstrapping script

Identify a workflow file that you would like to debug. Open it in your code editor and locate the import statements at the top. Add the bootstrapping script immediately after these imports.

```python
# Your existing imports are above this line

# ------ Begin Bootstrapping Script ------
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest

load_lib_request = RegisterLibraryFromFileRequest(
    file_path="<library path here>",
    load_as_default_library=True,
)
load_lib_result = GriptapeNodes.handle_request(load_lib_request)

GriptapeNodes.ContextManager().push_workflow("<flow name from your workflow>")
    flow.execute()
# ------ End Bootstrapping Script ------

# Rest of your workflow code continues below
```

### 2. Configure the script

Update two critical parts of the script:

1. **Set the library path**:

    - In the boostrapping script replace `FILE_PATH = "<library path here>"` with the actual path from your configuration editor
    - Example: `FILE_PATH = "/Users/<yourname>/.local/share/griptape_nodes/libraries/griptape_nodes_library/griptape_nodes_library.json"`

1. **Set the flow name**:

    - In the boostrapping script replace `"<flow name from your workflow>"` with the actual flow name from your workflow file

    - Look for the flow name in lines near the top that contain `CreateFlowRequest` or `cmd.create_flow`

        - `GriptapeNodes.handle_request(CreateFlowRequest(request_id=None, parent_flow_name=None, flow_name='ControlFlow_1', set_as_new_context=True))`

        - `cmd.create_flow(flow_name="ControlFlow_1")`

        - The flow name you're looking for from both of these examples would be: `ControlFlow_1`

### 3. Save your changes

Save the modified workflow file.

## Running and Debugging

### To debug the workflow:

1. Set breakpoints in your editor
1. Run the file in debug mode through your editor
1. When execution reaches a breakpoint, it will pause
1. Inspect variables and step through code using your editor's debug tools

## Troubleshooting

### If your script doesn't run:

- Verify the file path points to the correct node library
- Check that the flow name exactly matches what's in your `create_flow()` or `CreateFlowRequest` command

## Notes

- If your workflow uses multiple libraries, you'll need to register each one
- The bootstrapping script should be removed before committing your workflow file
