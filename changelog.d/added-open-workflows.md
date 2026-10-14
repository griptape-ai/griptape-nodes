- The engine can hold several workflows open at once. `ActivateWorkflowRequest` switches between
  them without reloading, `ListOpenWorkflowsRequest` lists them, and `CloseWorkflowRequest` closes
  one. `ClearAllObjectStateRequest` now clears only the active workflow.
