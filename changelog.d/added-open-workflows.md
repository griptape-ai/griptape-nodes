- The engine can hold several workflows open at once. `ActivateWorkflowRequest` switches between
  them without reloading, even while one is running, `ListOpenWorkflowsRequest` lists them, and
  `CloseWorkflowRequest` closes one. Only one workflow runs at a time, and run events name their
  workflow in `ExecutionEvent.workflow_name`. `ClearAllObjectStateRequest` now clears only the
  active workflow.
