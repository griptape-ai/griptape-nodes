- Merging a branch from the workflow list while the branch or its source is open on the canvas
  now fails with a message asking you to open another workflow first. Before, merging the open
  branch deleted its file and left the canvas on a workflow that no longer existed, and merging
  into the open source was undone the next time the source was saved.
