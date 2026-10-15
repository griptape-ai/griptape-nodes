- The editor can keep several workflows open in tabs, and switch between them without reloading,
  even while one runs. See
  [Working with several workflows](docs/guides/editor/running_workflows.md#working-with-several-workflows).
  `OpenWorkflowRequest`, `ListOpenWorkflowsRequest`, and `CloseWorkflowRequest` manage the open
  workflows. A request about one workflow takes its `workflow_id`, and with several open, one that
  names none fails instead of guessing. Results and run events carry `scope`, `workflow_id`, and
  `run_id`. One workflow runs at a time, and **Reload Libraries**, renaming, moving, and saving keep
  each workflow open with the same `workflow_id`.
