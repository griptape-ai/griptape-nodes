- Naming a saved workflow by its registry name (`workflow_name`, `name`, `template_name`, or
  `compare_workflow_name`) is deprecated on the requests that act on one; send its `workflow_id`,
  from each entry of `ListAllWorkflowsResultSuccess.workflows`, instead. The name fields are
  removed once every engine the editor supports reports workflow ids.
