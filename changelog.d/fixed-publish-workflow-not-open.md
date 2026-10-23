- `PublishWorkflowRequest` and `GetPublishOptionsRequest` for a workflow that is not open now fail
  instead of saving the open workflow over that workflow's file. Open the workflow, then publish
  it. A publish whose save of the open workflow fails now fails too, instead of publishing the file
  as it was last saved.
