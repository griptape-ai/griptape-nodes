- **Breaking:** The `WorkflowRegistry` classmethods `generate_new_workflow`, `ensure_unsaved`,
  `delete_workflow_by_name`, `clear_user_workflows`, and `rekey_workflow` are removed. Use
  `RegisterWorkflowRequest`, `SetWorkflowContextRequest`, `DeleteWorkflowRequest`,
  `RefreshWorkflowRegistryRequest`, and `MoveWorkflowRequest` or `RenameWorkflowRequest` instead.
