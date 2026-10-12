- With the "Ask before the chat agent runs things" beta feature on, the chat agent asks before it
  runs workflows or nodes, generates images, or uses tools from your own MCP servers, so a
  question no longer spends credits unprompted. A paused turn lists its calls in
  `pending_approvals` on `RunAgentResultSuccess`, and `ResolveToolApprovalsRequest` answers them.
  [#5606](https://github.com/griptape-ai/griptape-nodes-engine/issues/5606)
