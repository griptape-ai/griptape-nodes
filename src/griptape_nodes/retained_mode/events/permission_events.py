"""Events for the permission system.

`PermissionDecisionEvent` is broadcast for every evaluation; audit log
listeners and editor UIs subscribe to it. The request types let callers
read the effective policy, tail recent decisions, and grant/revoke rules
through the standard request dispatcher.
"""

from dataclasses import dataclass, field
from typing import Any

from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class PermissionDecisionEvent(AppPayload):
    """Broadcast after every `PermissionManager` evaluation. Informational.

    `rule_id` is None when the policy fell through to its default decision.
    `inspected_paths` records which match-paths the rule actually consulted,
    making "explain why this fired" trivially debuggable. `inspected_values`
    is scoped to the matching rule (empty on default fall-through) and maps
    each consulted path to the resolved value the matcher saw, so consumers
    can render "why" without re-running the matcher.
    """

    rule_id: str | None
    decision: str
    principal_kind: str
    principal_label: str
    action_request_type: str
    resource_summary: dict[str, Any] = field(default_factory=dict)
    inspected_paths: list[str] = field(default_factory=list)
    inspected_values: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


@dataclass
@PayloadRegistry.register
class GetEffectivePolicyRequest(RequestPayload):
    """Read the merged permission policy as seen by the engine."""


@dataclass
@PayloadRegistry.register
class GetEffectivePolicyResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    policy: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GetEffectivePolicyResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class ListPermissionDecisionsRequest(RequestPayload):
    """Read recent permission decisions from the in-memory ring buffer."""

    limit: int | None = None


@dataclass
@PayloadRegistry.register
class ListPermissionDecisionsResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    decisions: list[dict[str, Any]]


@dataclass
@PayloadRegistry.register
class ListPermissionDecisionsResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class GrantPermissionRuleRequest(RequestPayload):
    """Append a rule to the active policy."""

    rule: dict[str, Any]


@dataclass
@PayloadRegistry.register
class GrantPermissionRuleResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    rule_id: str


@dataclass
@PayloadRegistry.register
class GrantPermissionRuleResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass


@dataclass
@PayloadRegistry.register
class RevokePermissionRuleRequest(RequestPayload):
    """Remove a rule by id from the active policy."""

    rule_id: str


@dataclass
@PayloadRegistry.register
class RevokePermissionRuleResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    rule_id: str


@dataclass
@PayloadRegistry.register
class RevokePermissionRuleResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    pass
