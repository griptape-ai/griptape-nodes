# Execution Events Reference

While Griptape Nodes runs a workflow, it sends execution events that describe what is
happening. A library listens for them with
[`get_execution_event_listeners`](../development/custom_nodes/advanced_libraries.md#get_execution_event_listeners).

This page covers the two events for watching node runs, `NodeStartProcessEvent` and
`NodeFinishProcessEvent`. For a working library that uses them, see
[Example: a library that times every node run](../development/custom_nodes/advanced_libraries.md#example-a-library-that-times-every-node-run).

```python
from griptape_nodes.retained_mode.events.execution_events import (
    NodeFinishProcessEvent,
    NodeProcessOutcome,
    NodeStartProcessEvent,
)
```

## Node runs

`NodeStartProcessEvent` is sent when a node is about to run, before it does any work.
`NodeFinishProcessEvent` is sent when that run is over, whether it succeeded, failed, or
was cancelled.

Every node a workflow runs sends both: regular nodes, groups and loops, and the nodes
inside them. A node inside a loop sends a pair for every iteration.

### Fields

| Field                   | On     | Meaning                                                                                                       |
| ----------------------- | ------ | ------------------------------------------------------------------------------------------------------------- |
| `node_name`             | Both   | The node's name, as it appears on the canvas. A node inside a loop keeps its own name on every iteration.     |
| `node_type`             | Both   | The node's class name.                                                                                        |
| `specific_library_name` | Both   | The library the node comes from.                                                                              |
| `flow_name`             | Both   | The flow the node is in.                                                                                      |
| `execution_id`          | Both   | Identifies one run of one node. A run's start and finish share it.                                            |
| `parent_execution_id`   | Both   | The `execution_id` of the group or loop this run is part of, or `None` when the node isn't inside one.        |
| `outcome`               | Finish | How the run ended: `succeeded`, `failed`, or `cancelled`. Compare it with `NodeProcessOutcome`.               |
| `error_message`         | Finish | When the run failed, what went wrong, as one line of text.                                                    |
| `error`                 | Finish | When the run failed, the same error in parts, such as the message and the error type, as on `NodeErrorEvent`. |

### Outcomes

- **`succeeded`**: the node finished its work.
- **`failed`**: the node ran into an error. `error_message` and `error` say what went wrong.
    A node that runs into an error after the user asked it to stop still counts as
    `failed`.
- **`cancelled`**: the run was stopped, for example because the user cancelled the
    workflow, or the node stopped early because it was asked to.

### Matching a finish to its start

Use `execution_id`, not `node_name`. A loop set to **Run Group Items All at Once** runs
the nodes inside it at the same time, so the same node can have several runs going at
once.

### Nesting

`parent_execution_id` links each run to the group or loop it is part of. The nodes inside
a loop point at the loop's run, and a loop inside a group points at the group's run, so
you can rebuild the whole tree of a workflow run.

### Nodes that send no events

- **Locked nodes.** They keep their values without running.
- **Start Loop nodes.** The loop is reported by its End Loop node, whose events cover the
    whole loop.
- **Nodes that fail before they start**, for example because an input couldn't be read or
    the node failed validation. These send a `NodeErrorEvent` instead.

### Groups that run in their own environment

A group set to **Isolated Execution**, or to run in a library's environment, can run its
nodes in a separate Griptape Nodes process. Your library loads there too, so its
listeners hear those nodes there, and the main process hears only the group node itself.
