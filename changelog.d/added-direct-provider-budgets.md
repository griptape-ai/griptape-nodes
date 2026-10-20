- Nodes that call a model provider directly, rather than through Griptape Cloud, can now take part
  in Griptape Cloud spending budgets. `BudgetAccessRequest` asks Cloud before the call and fails
  with the same "Budget stopped this run." message when a budget refuses it; if Cloud cannot be
  reached the call goes ahead. `ReportUsageRequest` sends the call's token counts afterwards, in the
  background, and Cloud prices them. Both carry the run's id, which the new `FlowRunStartedEvent`
  announces and `ControlFlowResolvedEvent` and `ControlFlowCancelledEvent` repeat as `run_id`.
  See [Budgets for Direct Provider Calls](https://docs.griptapenodes.com/en/stable/development/custom_nodes/direct_provider_budgets/).
  [#5422](https://github.com/griptape-ai/griptape-nodes-engine/issues/5422)
  [#5945](https://github.com/griptape-ai/griptape-nodes-engine/issues/5945)
