- Changes to a workflow can be undone and redone, up to the last 100. Each action undoes as one
  step, such as dragging several nodes or pasting a group. Running and saving are never undone.
  Clients mark which action a request belongs to with the new `undo_group` field and send
  `UndoRequest` and `RedoRequest`; `UndoHistoryChanged` tells them what Undo and Redo will do. See
  [Undo and Redo](https://docs.griptapenodes.com/en/stable/guides/editor/undo_and_redo/).
  [#2561](https://github.com/griptape-ai/griptape-nodes-engine/issues/2561)
