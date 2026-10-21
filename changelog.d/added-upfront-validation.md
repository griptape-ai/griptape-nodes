- Running a flow now checks, before anything runs, every node whose inputs are already known: values
  set on the node, or outputs of nodes this run won't re-run. If any of their checks fail, the flow
  doesn't start, and every problem shows on its node at once instead of one per run. Nodes whose
  inputs come from nodes that will run are still checked just before they run.
  [#5963](https://github.com/griptape-ai/griptape-nodes-engine/issues/5963)
