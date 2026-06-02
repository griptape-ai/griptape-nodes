# Strict Mode Reference

Strict mode is a runtime contract for what node code is allowed to do
across the orchestrator and worker subprocess. When a node violates the
contract, the framework records a named violation and routes it to the
node's result payload so the author sees a remediation message in the
editor instead of a silent no-op, deadlock, or a stack trace that names
the wrong layer.

Strict mode is always on. There is no config flag, env var, or runtime
toggle. Severity is picked per-rule: correctness rules fail execution;
ergonomics rules emit a warning.

## How it surfaces

Violations attach to the `ResultDetails` on the outgoing
`ResultPayload`. In the editor, the node's output panel shows the rule
id, severity, and remediation. On the worker side, correctness
violations elevate a successful `ExecuteNodeResultSuccess` to an
`ExecuteNodeResultFailure`; ergonomics violations stay non-fatal.

Violations are also logged through the `griptape_nodes.strict_mode`
logger. Set it to `WARNING` or lower to see every violation in the
console.

## Scope kinds

A strict-mode scope is opened by the framework for the duration of a
particular operation. Detectors report against whichever scope is
currently active; outside a scope, reports are dropped.

- `RUNTIME_EXECUTE`: opened around
    `NodeManager.on_execute_node_request` for a single node's execution.
    Violations here attach to the execution's `ResultPayload`.
- `LOAD_PROBE`: opened around a single node class's schema probe in
    `LibraryManager._serialize_library_node_schemas`. Violations here
    can exclude the class from the exported schema (for correctness
    rules) or simply warn (for ergonomics rules).

## Rule catalog

The authoritative source is
[`common/strict_mode_checks.py`](https://github.com/griptape-ai/griptape-nodes/blob/main/src/griptape_nodes/common/strict_mode_checks.py).
Each rule is either a **correctness** rule (fails on both orchestrator
and worker) or an **ergonomics** rule (warns on orchestrator, escalates
to a failure on the worker unless `worker_escalation=False`).

### Correctness rules (fail execution)

#### `reentrant-bus-in-init`

A node issued an event-bus request from inside its `__init__`. The
worker library probe runs `__init__` to extract a schema; re-entering
the bus there deadlocks the worker.

**Remediation**: move the call into `aprocess` (or a lifecycle hook
that runs after construction).

#### `unknown-payload-type`

A payload type crossing the wire was not registered in
`PayloadRegistry`. Unknown types cannot be deserialized safely by the
cattrs converter.

**Remediation**: decorate the payload class with
`@PayloadRegistry.register` so it can cross the
worker/orchestrator boundary.

### Ergonomics rules (warnings)

#### `parameter-behaviors-dropped-in-schema`

A `Parameter` attached `converters`, `validators`, or `traits` that
are not captured in the worker schema. The orchestrator stub cannot
re-run those behaviors, so UI-side behavior diverges from worker-side
execution.

This rule does **not** escalate on the worker (`worker_escalation=False`)
because it is reported during library load and escalation would skip
the class entirely.

**Remediation**: move behavior that needs to run on both sides into
the worker-side `aprocess`, or accept the divergence as
orchestrator-only UI sugar.

#### `parameter-mutation-during-aprocess`

A node called `add_parameter` or `remove_parameter_element` during
`aprocess`. On the worker, these mutations apply to the transient
node instance and do not sync back to the orchestrator.

Detection is keyed on `aprocess_scope()`, which the framework opens
only around `await node.aprocess()`. Hydration-time mutations made
from `before_value_set` / `after_value_set` (the standard dynamic-
parameter pattern) do **not** trip this rule, even though they share
the surrounding `RUNTIME_EXECUTE` strict-mode scope.

**Remediation**: emit an `AddParameterToNodeRequest` or
`RemoveParameterFromNodeRequest` (both `ForwardFromWorkerMixin`) so
the mutation propagates to the authoritative orchestrator-side node.

Handler code that reaches these methods via the request path is
sanctioned: the handler wraps its call in
`sanctioned_parameter_mutation()` so the detector does not
false-positive on legitimate request-driven mutations.

#### `worker-reach-into-orchestrator`

A node running on a worker issued a request whose authoritative state
lives on the orchestrator (flow graph, connections, parameter
registry, config, secrets). The request is forwarded across the
WebSocket bus; each call is a network round-trip and the returned
view is stale-by-call.

Detection runs at the `RemoteHandler` dispatch site, which is gated
by `EventManager.worker_node_execution_scope` -- opened by
`NodeManager._hydrate_and_run_node_inner` around BOTH input
hydration and `aprocess`. A forwarded request issued from
`before_value_set` / `after_value_set` will trip this rule even
though no `aprocess()` has run yet; the remediation message says
"during node execution" rather than "from aprocess" for that reason.

This rule does **not** escalate on the worker
(`worker_escalation=False`) because every forwarded request would
otherwise become a node failure -- the calls succeed, they are just
expensive. The point is to surface the round-trip so authors can
choose to pass data in via parameters instead of fetching per-call.

**Known blind spot**: violations issued from library-internal helper
threads (e.g. `ThreadPoolExecutor` inside diffusers / transformers)
are not reported. The strict-mode reporter is task-local, so a
helper thread's `STRICT_MODE.report` finds no active scope and
no-ops. The forward still proceeds normally; only the rule's
recording is silent.

**Remediation**: if this is an intentional write (e.g. publishing a
parameter value), ignore the warning. If this is a read of flow /
connection state, consider whether the data could be passed in via
parameters instead of fetched per-call.

## Adding a new rule

1. Add a `StrictModeRule` entry to `RULES` in
    [`common/strict_mode_checks.py`](https://github.com/griptape-ai/griptape-nodes/blob/main/src/griptape_nodes/common/strict_mode_checks.py).
    Pick `correctness=True` if the violation makes the system produce
    wrong or inconsistent results; otherwise `correctness=False`. Set
    `worker_escalation=False` only if the rule is reported outside
    per-node execution and escalation would drop the class entirely
    (like `LOAD_PROBE`-scoped warnings).

1. Report the violation at the call site:

    ```python
    from griptape_nodes.common.strict_mode import STRICT_MODE
    from griptape_nodes.common.strict_mode_checks import RULES

    rule = RULES["my-rule-id"]
    STRICT_MODE.report(
        rule_id=rule.rule_id,
        message=rule.render(some_field="value"),
    )
    ```

1. The strict-mode reporter is task-local: `STRICT_MODE.report` reads
    the active scope from a `ContextVar`, so a detector running on a
    helper thread (e.g. one spawned by a third-party library's
    `ThreadPoolExecutor`) finds no active scope and the report is
    dropped silently. Detectors in that situation cannot record
    violations against the originating node's scope. Either run the
    detector on the asyncio task that owns the scope, or accept the
    blind spot and document it on the rule's `description`.

1. Add a unit test that opens a scope, triggers the detector, and
    asserts `scope.violations[0].rule_id` and severity. See
    [`tests/unit/exe_types/test_parameter_mutation_strict_mode.py`](https://github.com/griptape-ai/griptape-nodes/blob/main/tests/unit/exe_types/test_parameter_mutation_strict_mode.py)
    for a minimal template.
