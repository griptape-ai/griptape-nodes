- **Breaking:** `SetWorkflowContextRequest` now fails when `workflow_name` names no registered
  workflow (an `unsaved:<id>` name still registers a new unsaved workflow).
  `EnsureWorkflowAndFlowRequest` with such a name now creates a new unsaved workflow with that
  display name, and its result reports the workflow's own `unsaved:<id>` name instead of the name
  sent. Omit `workflow_name` to create a new workflow and use the name in the result, or save the
  workflow first.
