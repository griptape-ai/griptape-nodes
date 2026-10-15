- The engine can hold several workflows open at once. `ActivateWorkflowRequest` switches between
  them without reloading, even while one is running, `ListOpenWorkflowsRequest` lists them, and
  `CloseWorkflowRequest` closes one. Only one workflow runs at a time. Run events and requests name
  the workflow they came from in `source_workflow_name`, so a client showing several workflows can
  route each to the right one. `ClearAllObjectStateRequest` now clears only the active workflow.
