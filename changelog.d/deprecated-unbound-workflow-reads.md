- A thread a node library starts without copying its context, which then calls the engine while
  several workflows are open, is given the running workflow and logs a warning. Start such threads
  with `contextvars.copy_context().run`, or emit through the node, so they keep their workflow. The
  fallback will be removed in a later release. See
  [MIGRATION.md](MIGRATION.md#threads-a-node-starts-keep-their-workflow).
