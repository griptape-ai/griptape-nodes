- **Breaking:** The chat agent now asks before it runs workflows or nodes, generates images, or uses
  tools from your own MCP servers, so a question no longer spends credits unprompted. Such a turn
  ends `RunAgentRequest` with the calls in `output.pending_approvals` instead of running them, and
  they run only once a client answers with `ResolveToolApprovalsRequest`; see
  [Approvals](docs/guides/agent/approvals.md).
  [#5606](https://github.com/griptape-ai/griptape-nodes-engine/issues/5606)
