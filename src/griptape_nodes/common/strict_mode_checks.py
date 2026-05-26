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
    worker_escalation: bool = True

    def render(self, **context: Any) -> str:
        return self.remediation_template.format(**context)


RULES: dict[str, StrictModeRule] = {
    "reentrant-bus-in-init": StrictModeRule(
        rule_id="reentrant-bus-in-init",
        default_severity=StrictModeSeverity.ERROR,
        correctness=True,
        description=(
            "A node issued an event-bus request from inside its __init__. "
            "The worker library probe runs __init__ to extract a schema; "
            "re-entering the bus there deadlocks the worker."
        ),
        remediation_template=(
            "Node class '{node_class}' issued '{request_type}' during __init__. "
            "Move the call into aprocess (or a lifecycle hook that runs after "
            "construction)."
        ),
    ),
}
