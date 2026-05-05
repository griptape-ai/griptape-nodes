"""Strict-mode rule registry.

Central catalog of every strict-mode rule: its stable ``rule_id``,
default severity, whether it is a correctness-class violation (failed
even on the orchestrator) or an ergonomics-class warning (worker-only
escalation), a human description, and a ``str.format``-ready
remediation template.

Detectors import ``RULES`` to look up their rule and call
``report_violation(rule_id=..., message=RULES[rid].render(...))`` at
their own call site. No enforcement logic lives here -- this module
is a static catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from griptape_nodes.common.strict_mode import StrictModeSeverity


@dataclass(frozen=True)
class StrictModeRule:
    """Static description of a single strict-mode rule.

    ``correctness`` rules are rules whose violation means the system is
    in a state that cannot produce correct results (deadlocks, lost
    data, state that silently disagrees between orchestrator and
    worker). These fail on both sides. ``correctness=False`` rules
    describe ergonomics or API-shape issues where the system still
    runs -- they warn on the orchestrator and escalate to a failure on
    the worker because the worker's stateless model makes them
    load-bearing.
    """

    rule_id: str
    default_severity: StrictModeSeverity
    correctness: bool
    description: str
    remediation_template: str

    def render(self, **context: Any) -> str:
        return self.remediation_template.format(**context)


def _rule(
    rule_id: str,
    *,
    severity: StrictModeSeverity,
    correctness: bool,
    description: str,
    remediation: str,
) -> StrictModeRule:
    return StrictModeRule(
        rule_id=rule_id,
        default_severity=severity,
        correctness=correctness,
        description=description,
        remediation_template=remediation,
    )


RULES: dict[str, StrictModeRule] = {
    rule.rule_id: rule
    for rule in (
        _rule(
            "sync-in-async-loop",
            severity=StrictModeSeverity.ERROR,
            correctness=True,
            description=(
                "A synchronous GriptapeNodes.handle_request or broadcast_app_event "
                "was invoked from within a running event loop against an async "
                "handler. This deadlocks or stalls the loop."
            ),
            remediation=(
                "Request '{request_type}' was dispatched synchronously from a running "
                "event loop against an async handler ({handler_description}). "
                "Call {recommended_call} instead."
            ),
        ),
        _rule(
            "reentrant-bus-in-init",
            severity=StrictModeSeverity.ERROR,
            correctness=True,
            description=(
                "A node issued an event-bus request from inside its __init__. "
                "The worker library probe runs __init__ to extract a schema; "
                "re-entering the bus there deadlocks the worker."
            ),
            remediation=(
                "Node class '{node_class}' issued '{request_type}' during __init__. "
                "Move the call into aprocess (or a lifecycle hook that runs after "
                "construction)."
            ),
        ),
        _rule(
            "unknown-payload-type",
            severity=StrictModeSeverity.ERROR,
            correctness=True,
            description=(
                "A payload type crossing the wire was not registered in "
                "PayloadRegistry. Unknown types cannot be deserialized safely."
            ),
            remediation=(
                "Payload type '{type_name}' is not registered. Decorate its "
                "class with @PayloadRegistry.register so it can cross the "
                "worker/orchestrator boundary."
            ),
        ),
        _rule(
            "local-only-state-access-from-worker",
            severity=StrictModeSeverity.ERROR,
            correctness=True,
            description=(
                "A worker-side node issued a request whose handler reads "
                "orchestrator-only state (flow, connections, context). The "
                "request is not ForwardFromWorkerMixin, so it cannot cross "
                "back to the orchestrator."
            ),
            remediation=(
                "Node on worker issued '{request_type}', which touches "
                "orchestrator-only state ({manager}). Mark the request type "
                "with ForwardFromWorkerMixin or avoid the call from worker-side "
                "node code."
            ),
        ),
        _rule(
            "drag-load-bypass",
            severity=StrictModeSeverity.ERROR,
            correctness=True,
            description=(
                "BaseNode.aprocess was invoked outside of a RUNTIME_EXECUTE "
                "scope on the worker. The drag-load UI path calls "
                "node.process() directly on the orchestrator, which silently "
                "no-ops for worker libraries."
            ),
            remediation=(
                "Node class '{node_class}' was executed outside an "
                "ExecuteNodeRequest on the worker path. Route through "
                "ExecuteNodeRequest so the stateless worker sees a well-formed "
                "request."
            ),
        ),
        _rule(
            "worker-library-version-mismatch",
            severity=StrictModeSeverity.ERROR,
            correctness=True,
            description=(
                "Worker's loaded library disagrees with the orchestrator's "
                "registered library on version or identity. Parameter specs "
                "may drift, producing silently incorrect runs."
            ),
            remediation=(
                "Library '{library_name}' version '{worker_version}' on worker "
                "does not match orchestrator version '{orchestrator_version}'. "
                "Reinstall the library on the worker or restart the engine."
            ),
        ),
        _rule(
            "exception-fidelity-lost",
            severity=StrictModeSeverity.ERROR,
            correctness=True,
            description=(
                "A worker-side exception could not be serialized with full "
                "fidelity (type, message, traceback) when forwarded to the "
                "orchestrator. The caller sees only a stringified summary."
            ),
            remediation=(
                "Exception of type '{exception_class}' lost '{missing_field}' "
                "when crossing the wire. Ensure the exception class is "
                "picklable or expose the failing field as a serializable "
                "attribute."
            ),
        ),
        _rule(
            "parameter-behaviors-dropped-in-schema",
            severity=StrictModeSeverity.WARNING,
            correctness=False,
            description=(
                "A Parameter attached converters, validators, or traits that "
                "are not captured in the worker schema. Orchestrator-side UI "
                "behavior and worker-side execution diverge."
            ),
            remediation=(
                "Parameter '{parameter_name}' carries {dropped_attributes} that "
                "are not serialized into the worker schema. These will not "
                "execute on the orchestrator stub; behavior may differ from "
                "a local-library node."
            ),
        ),
        _rule(
            "parameter-mutation-during-aprocess",
            severity=StrictModeSeverity.WARNING,
            correctness=False,
            description=(
                "A node called add_parameter or remove_parameter during "
                "aprocess. On the worker these changes are local to the "
                "transient node and do not sync back to the orchestrator."
            ),
            remediation=(
                "Node mutated parameter '{parameter_name}' during aprocess via "
                "{mutation}. Emit AddParameterRequest or "
                "RemoveParameterFromNodeRequest (both ForwardFromWorkerMixin) "
                "to propagate the change to the orchestrator."
            ),
        ),
        _rule(
            "partial-output-streaming-race",
            severity=StrictModeSeverity.WARNING,
            correctness=False,
            description=(
                "A node emitted a streaming parameter update fewer than "
                "STREAMING_RACE_THRESHOLD_MS milliseconds before its final "
                "ExecuteNodeResult. The two messages can arrive at the "
                "editor out of order."
            ),
            remediation=(
                "Node '{node_name}' published a streaming update {delta_ms}ms "
                "before the final result. Flush or drain partial outputs "
                "before returning from aprocess."
            ),
        ),
        _rule(
            "aprocess-thread-offload-sync-loop",
            severity=StrictModeSeverity.ERROR,
            correctness=True,
            description=(
                "A node override of aprocess ran sync code on the event loop "
                "that issued a synchronous handle_request against an async "
                "handler. The default thread-offloaded aprocess guards "
                "against this; custom overrides bypass the guard."
            ),
            remediation=(
                "Override of aprocess on '{node_class}' invoked sync "
                "handle_request for '{request_type}' on the event-loop thread. "
                "Call await ahandle_request, or route the sync work through "
                "asyncio.to_thread."
            ),
        ),
    )
}
