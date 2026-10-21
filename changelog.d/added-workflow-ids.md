- Every workflow now has a permanent `workflow_id`, saved in its file's metadata header, that stays
  the same when the workflow is saved, renamed, or moved and across restarts. Results that name a
  workflow now also report its id, such as `GetWorkflowContextSuccess.workflow_id`.
