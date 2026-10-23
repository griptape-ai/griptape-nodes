- **Breaking:** Opening a workflow a library provides, such as a Griptape-provided template, now
  opens an unsaved copy that you save like a new workflow, and the library's own file is never
  changed. `RunWorkflowFromRegistryResultSuccess` and the other `RunWorkflow*` results report
  the copy's `workflow_id` and the library workflow's id as `seeded_from_workflow_id`, and
  `SetWorkflowContextRequest` naming a library workflow now fails.
