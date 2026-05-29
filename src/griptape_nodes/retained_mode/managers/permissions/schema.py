"""Pydantic schema for the permission system.

The data model is principal/action/resource/context: rules describe WHO is
asking, WHAT they want to do, against WHICH resource, under WHICH ambient
facts. Each rule resolves to allow/deny/prompt; first-match-wins inside a
`PermissionPolicy`.

Predicate operators are encoded as a discriminated union (`MatchExpr`) so
policies round-trip cleanly through JSON config and Pydantic validation
catches typos at parse time. New operators slot in additively without
breaking the schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EqualsExpr(BaseModel):
    """Strict equality (`==`)."""

    op: Literal["equals"] = "equals"
    value: Any


class InExpr(BaseModel):
    """Membership (`value in values`).

    Against a list-valued field this uses any-overlap semantics: it matches when
    any element of the field is in `values`. An allow-list built this way lets a
    request through as soon as one element qualifies, even if other elements do
    not, so prefer per-element rules when every element must be vetted.
    """

    op: Literal["in"] = "in"
    values: list[Any]


class GlobExpr(BaseModel):
    """Case-sensitive, platform-independent fnmatch glob against a string field.

    `${...}` macros in `pattern` are expanded before matching. This is NOT
    path-aware: `*` spans `/`, and nothing is canonicalized, so `..` traversal
    is not collapsed. Use `PathUnderExpr` for filesystem containment checks.
    """

    op: Literal["glob"] = "glob"
    pattern: str


class PathUnderExpr(BaseModel):
    """Path containment after macro expansion + canonicalisation.

    Both target and `root` are expanded against the active workspace before
    comparison so policies can be authored in terms of `${workspace}/...`.
    """

    op: Literal["path_under"] = "path_under"
    root: str


class NotExpr(BaseModel):
    """Negation."""

    op: Literal["not"] = "not"
    expr: MatchExpr


class AllOfExpr(BaseModel):
    """Conjunction; matches when every sub-expression matches."""

    op: Literal["all_of"] = "all_of"
    exprs: list[MatchExpr]


class AnyOfExpr(BaseModel):
    """Disjunction; matches when any sub-expression matches."""

    op: Literal["any_of"] = "any_of"
    exprs: list[MatchExpr]


# `Annotated[X | ..., Field(discriminator="op")]` is Pydantic v2's discriminated-union
# idiom: each member carries a `op: Literal[...]` tag and Pydantic dispatches on it.
# Keeps unknown operators from silently parsing as the wrong shape.
MatchExpr = Annotated[
    EqualsExpr | InExpr | GlobExpr | PathUnderExpr | NotExpr | AllOfExpr | AnyOfExpr,
    Field(discriminator="op"),
]


class PrincipalKind(StrEnum):
    """Categories of actor that can issue a request."""

    ENGINE = "engine"
    NODE = "node"
    CLIENT = "client"


class PrincipalMatch(BaseModel):
    """Match the actor that issued the request.

    Populated fields are AND'd; unpopulated fields are wildcards.
    """

    kind: list[PrincipalKind] | None = None
    library: MatchExpr | None = None
    node_type: MatchExpr | None = None
    topic: MatchExpr | None = None


class ActionMatch(BaseModel):
    """Match by `RequestPayload` class name (must be registered in PayloadRegistry)."""

    request_type: MatchExpr


class ResourceMatch(BaseModel):
    """Match against fields of the request payload via dot-paths.

    Keys are dot-paths into the request dataclass (resolved with the same
    semantics as `ConfigManager.get_dot_value`). All entries must match (AND).
    """

    fields: dict[str, MatchExpr] = Field(default_factory=dict)


class ContextMatch(BaseModel):
    """Match against the merged fact tree.

    Keys are dot-paths into the merged facts dict. All entries must match (AND).
    """

    facts: dict[str, MatchExpr] = Field(default_factory=dict)


class WhenClause(BaseModel):
    """Combined matcher. Populated axes are AND'd; unpopulated axes are wildcards."""

    principal: PrincipalMatch | None = None
    action: ActionMatch | None = None
    resource: ResourceMatch | None = None
    context: ContextMatch | None = None


class Decision(StrEnum):
    """Verdict produced by evaluating a rule or policy."""

    ALLOW = "allow"
    DENY = "deny"
    PROMPT = "prompt"


class PermissionRule(BaseModel):
    """A single rule. First match wins inside a `PermissionPolicy`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    when: WhenClause = Field(default_factory=WhenClause)
    decision: Decision
    reason: str | None = None
    granted_by: str | None = None


class PermissionPolicy(BaseModel):
    """An ordered list of rules plus a fall-through default decision.

    The default decision is `ALLOW` so an unconfigured engine behaves exactly
    as it did before this manager existed. Operators ratchet down by adding
    explicit deny rules, or by setting `default_decision` to `DENY` /`PROMPT`
    once they have built up an allow list.
    """

    model_config = ConfigDict(extra="forbid")

    rules: list[PermissionRule] = Field(default_factory=list)
    default_decision: Decision = Decision.ALLOW


class PermissionSettings(BaseModel):
    """Top-level permission settings; merged into `Settings`."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    consent_prompts_enabled: bool = True
    audit_log_max_entries: int = 1000
    policy: PermissionPolicy = Field(default_factory=PermissionPolicy)


# Forward-references for the recursive operators.
NotExpr.model_rebuild()
AllOfExpr.model_rebuild()
AnyOfExpr.model_rebuild()
