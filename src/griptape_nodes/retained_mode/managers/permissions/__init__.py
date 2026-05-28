"""Permission system: declarative policy over privileged engine operations.

The schema (`schema`), matcher engine (`matchers`), and fact registry (`facts`)
are exposed here for use by `PermissionManager` and tests. Public consumers
should reach for `PermissionManager` rather than these modules directly.
"""

from griptape_nodes.retained_mode.managers.permissions.facts import (
    FactInvalidator,
    FactRegistry,
    RequestFactEnricher,
)
from griptape_nodes.retained_mode.managers.permissions.matchers import (
    EvaluationResult,
    Principal,
    PrincipalKind,
    evaluate_policy,
    evaluate_rule,
)
from griptape_nodes.retained_mode.managers.permissions.schema import (
    ActionMatch,
    AllOfExpr,
    AnyOfExpr,
    ContextMatch,
    Decision,
    EqualsExpr,
    GlobExpr,
    InExpr,
    MatchExpr,
    NotExpr,
    PathUnderExpr,
    PermissionPolicy,
    PermissionRule,
    PermissionSettings,
    PrincipalMatch,
    ResourceMatch,
    WhenClause,
)

__all__ = [
    "ActionMatch",
    "AllOfExpr",
    "AnyOfExpr",
    "ContextMatch",
    "Decision",
    "EqualsExpr",
    "EvaluationResult",
    "FactInvalidator",
    "FactRegistry",
    "GlobExpr",
    "InExpr",
    "MatchExpr",
    "NotExpr",
    "PathUnderExpr",
    "PermissionPolicy",
    "PermissionRule",
    "PermissionSettings",
    "Principal",
    "PrincipalKind",
    "PrincipalMatch",
    "RequestFactEnricher",
    "ResourceMatch",
    "WhenClause",
    "evaluate_policy",
    "evaluate_rule",
]
