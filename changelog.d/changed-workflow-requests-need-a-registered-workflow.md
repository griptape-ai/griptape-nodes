- **Breaking:** The requests that act on a saved workflow now fail when they name no registered
  workflow, instead of acting on the open one: `RenameWorkflowRequest` no longer saves the open
  workflow under the new name, `PublishWorkflowRequest` no longer saves the open workflow under the
  unknown name before publishing, and `GetPublishOptionsRequest` now checks the workflow exists.
