- The editor can keep several workflows open in tabs, and switch between them without reloading,
  even while one runs. See
  [Working with several workflows](docs/guides/editor/running_workflows.md#working-with-several-workflows).
  `OpenWorkflowRequest`, `ListOpenWorkflowsRequest`, and `CloseWorkflowRequest` manage the open
  workflows, and any request can act on one by naming its `workflow_id`. The engine names the
  workflow on every result and run event, and runs one workflow at a time. **Reload Libraries**
  reopens the saved workflows that were open.
