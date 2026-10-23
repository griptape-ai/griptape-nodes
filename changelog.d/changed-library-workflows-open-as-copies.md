- **Breaking:** Opening a workflow a library provides, such as a Griptape-provided template, now
  opens an unsaved copy that you save like a new workflow, and the library's own file is never
  changed. `RunWorkflowFromRegistryResultSuccess` and the other `RunWorkflow*` results report
  the copy's `workflow_id` and the library workflow's id as `seeded_from_workflow_id`.
  `SetWorkflowContextRequest` and `EnsureWorkflowAndFlowRequest` naming a library workflow now
  fail; open it with `RunWorkflowFromRegistryRequest` instead. Publishing an open copy is refused
  until you save it; before, it published the library's file without your edits.
