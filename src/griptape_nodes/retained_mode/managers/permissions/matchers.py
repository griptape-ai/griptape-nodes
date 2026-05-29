"""Predicate evaluation for permission rules.

`evaluate_policy` is the single entry point used by `PermissionManager`; it
drives `evaluate_rule` over the policy's rule list and falls through to the
default decision on no match.

Match expressions are evaluated against three kinds of input:

* `Principal` — runtime actor identity, supplied by the dispatcher hook.
* request fields — read off the `RequestPayload` via dot-path navigation.
* fact tree — merged dict published by `FactRegistry`.

Path expansion for `PathUnderExpr` honours `${workspace}` and
`${static_files_directory}` macros so policies can be authored portably.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from griptape_nodes.files.path_utils import canonicalize_for_identity
from griptape_nodes.retained_mode.managers.permissions.schema import (
    ActionMatch,
    AllOfExpr,
    AnyOfExpr,
    ContextMatch,
    Decision,
    EqualsExpr,
    GlobExpr,
    InExpr,
    NotExpr,
    PathUnderExpr,
    PermissionPolicy,
    PermissionRule,
    PrincipalKind,
    PrincipalMatch,
    ResourceMatch,
    WhenClause,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from griptape_nodes.retained_mode.managers.permissions.schema import MatchExpr


@dataclass(frozen=True)
class Principal:
    """Runtime actor identity passed into rule evaluation."""

    kind: PrincipalKind
    library: str | None = None
    node_type: str | None = None
    topic: str | None = None
    node_name: str | None = None

    def label(self) -> str:
        """Short human-readable form, e.g. ``node:lib/UpscaleNode``."""
        if self.kind is PrincipalKind.NODE:
            lib = self.library or "?"
            nt = self.node_type or "?"
            return f"node:{lib}/{nt}"
        if self.kind is PrincipalKind.CLIENT:
            return f"client:{self.topic or '?'}"
        return "engine"


@dataclass
class EvaluationResult:
    """Outcome of evaluating a `PermissionPolicy` against a request context.

    `inspected_paths` accumulates dot-paths consulted across every rule the
    matcher walked, in evaluation order. `inspected_values` is scoped to the
    rule that ultimately matched (or empty when the policy fell through to
    its default), and maps each consulted dot-path to the resolved value the
    matcher saw. The user-facing denial message renders the latter so callers
    can tell why a request was blocked without re-running the matcher.
    """

    decision: Decision
    matched_rule: PermissionRule | None
    inspected_paths: list[str] = field(default_factory=list)
    inspected_values: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


def evaluate_policy(  # noqa: PLR0913
    policy: PermissionPolicy,
    *,
    principal: Principal,
    request_type_name: str,
    request_fields: Mapping[str, Any],
    facts: Mapping[str, Any],
    macro_context: Mapping[str, str] | None = None,
) -> EvaluationResult:
    """Evaluate `policy` against a single request context.

    First-match-wins: returns the first rule whose `when` clause matches.
    Falls through to `policy.default_decision` if no rule matches.
    """
    inspected: list[str] = []
    macros = dict(macro_context) if macro_context else {}
    for rule in policy.rules:
        rule_values: dict[str, Any] = {}
        matched = _matches_when(
            rule.when,
            principal=principal,
            request_type_name=request_type_name,
            request_fields=request_fields,
            facts=facts,
            macros=macros,
            inspected=inspected,
            inspected_values=rule_values,
        )
        if matched:
            return EvaluationResult(
                decision=rule.decision,
                matched_rule=rule,
                inspected_paths=inspected,
                inspected_values=rule_values,
                reason=rule.reason,
            )
    return EvaluationResult(
        decision=policy.default_decision,
        matched_rule=None,
        inspected_paths=inspected,
        inspected_values={},
        reason=None,
    )


def evaluate_rule(  # noqa: PLR0913
    rule: PermissionRule,
    *,
    principal: Principal,
    request_type_name: str,
    request_fields: Mapping[str, Any],
    facts: Mapping[str, Any],
    macro_context: Mapping[str, str] | None = None,
) -> bool:
    """Evaluate a single rule's `when` clause; primarily useful for tests."""
    inspected: list[str] = []
    inspected_values: dict[str, Any] = {}
    macros = dict(macro_context) if macro_context else {}
    return _matches_when(
        rule.when,
        principal=principal,
        request_type_name=request_type_name,
        request_fields=request_fields,
        facts=facts,
        macros=macros,
        inspected=inspected,
        inspected_values=inspected_values,
    )


def _matches_when(  # noqa: PLR0913
    when: WhenClause,
    *,
    principal: Principal,
    request_type_name: str,
    request_fields: Mapping[str, Any],
    facts: Mapping[str, Any],
    macros: Mapping[str, str],
    inspected: list[str],
    inspected_values: dict[str, Any],
) -> bool:
    if when.principal is not None and not _matches_principal(
        when.principal, principal, inspected, inspected_values, macros
    ):
        return False
    if when.action is not None and not _matches_action(
        when.action, request_type_name, inspected, inspected_values, macros
    ):
        return False
    if when.resource is not None and not _matches_resource(
        when.resource, request_fields, inspected, inspected_values, macros
    ):
        return False
    return not (
        when.context is not None and not _matches_context(when.context, facts, inspected, inspected_values, macros)
    )


def _matches_principal(
    match: PrincipalMatch,
    principal: Principal,
    inspected: list[str],
    inspected_values: dict[str, Any],
    macros: Mapping[str, str],
) -> bool:
    inspected.append("principal.kind")
    inspected_values["principal.kind"] = principal.kind.value
    if match.kind is not None and principal.kind not in match.kind:
        return False
    if match.library is not None:
        inspected.append("principal.library")
        inspected_values["principal.library"] = principal.library
        if not _eval_match(match.library, principal.library, macros):
            return False
    if match.node_type is not None:
        inspected.append("principal.node_type")
        inspected_values["principal.node_type"] = principal.node_type
        if not _eval_match(match.node_type, principal.node_type, macros):
            return False
    if match.topic is not None:
        inspected.append("principal.topic")
        inspected_values["principal.topic"] = principal.topic
        if not _eval_match(match.topic, principal.topic, macros):
            return False
    return True


def _matches_action(
    match: ActionMatch,
    request_type_name: str,
    inspected: list[str],
    inspected_values: dict[str, Any],
    macros: Mapping[str, str],
) -> bool:
    inspected.append("action.request_type")
    inspected_values["action.request_type"] = request_type_name
    return _eval_match(match.request_type, request_type_name, macros)


def _matches_resource(
    match: ResourceMatch,
    request_fields: Mapping[str, Any],
    inspected: list[str],
    inspected_values: dict[str, Any],
    macros: Mapping[str, str],
) -> bool:
    for path, expr in match.fields.items():
        key = f"resource.{path}"
        inspected.append(key)
        value = _resolve_dot_path(request_fields, path)
        inspected_values[key] = value
        if not _eval_match(expr, value, macros):
            return False
    return True


def _matches_context(
    match: ContextMatch,
    facts: Mapping[str, Any],
    inspected: list[str],
    inspected_values: dict[str, Any],
    macros: Mapping[str, str],
) -> bool:
    for path, expr in match.facts.items():
        key = f"context.{path}"
        inspected.append(key)
        value = _resolve_dot_path(facts, path)
        inspected_values[key] = value
        if not _eval_match(expr, value, macros):
            return False
    return True


def _eval_match(expr: MatchExpr, value: Any, macros: Mapping[str, str]) -> bool:  # noqa: PLR0911
    if isinstance(expr, EqualsExpr):
        return value == expr.value
    if isinstance(expr, InExpr):
        if isinstance(value, list):
            return any(item in expr.values for item in value)
        return value in expr.values
    if isinstance(expr, GlobExpr):
        if value is None:
            return False
        # `fnmatchcase` ignores OS path conventions so a policy matches identically
        # on every platform; plain `fnmatch` would case-fold and rewrite separators
        # on Windows, silently changing a security decision.
        pattern = _expand_macros(expr.pattern, macros)
        return fnmatch.fnmatchcase(str(value), pattern)
    if isinstance(expr, PathUnderExpr):
        return _path_under(value, expr.root, macros)
    if isinstance(expr, NotExpr):
        return not _eval_match(expr.expr, value, macros)
    if isinstance(expr, AllOfExpr):
        return all(_eval_match(sub, value, macros) for sub in expr.exprs)
    if isinstance(expr, AnyOfExpr):
        return any(_eval_match(sub, value, macros) for sub in expr.exprs)
    # A discriminated-union member with no handler is a programming error, not a
    # policy miss. Fail loud rather than silently returning False, which under a
    # surrounding `NotExpr` would invert into an unconditional allow.
    msg = f"Unhandled match expression type: {type(expr).__name__}"
    raise TypeError(msg)


def _path_under(value: Any, root_template: str, macros: Mapping[str, str]) -> bool:
    if value is None:
        return False
    target_str = _expand_macros(str(value), macros)
    root_str = _expand_macros(root_template, macros)
    # Anchor relative paths to the workspace, matching how the engine's file
    # boundary (`OSManager`) resolves request paths. Anchoring to CWD here would
    # judge a different path than the one actually read/written.
    workspace = macros.get("workspace")
    base = Path(workspace) if workspace else None
    try:
        target = canonicalize_for_identity(target_str, base=base)
        root = canonicalize_for_identity(root_str, base=base)
    except (OSError, ValueError):
        return False
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def _expand_macros(text: str, macros: Mapping[str, str]) -> str:
    """Replace `${name}` tokens with values from `macros`. Unknown tokens pass through.

    Intentionally simpler than `ParsedMacro`: rules need plain workspace-anchored
    paths, not the full template engine. If a richer surface is wanted later this
    function is the only place that needs to change.
    """
    if "${" not in text:
        return text
    out = text
    for key, replacement in macros.items():
        token = "${" + key + "}"
        if token in out:
            out = out.replace(token, replacement)
    return out


def _resolve_dot_path(data: Mapping[str, Any], path: str) -> Any:
    """Walk a dotted key into a nested mapping; returns None on any miss.

    Unlike `dict_utils.get_dot_value`, accepts dataclass-like objects via
    `getattr` fallback so request payloads can be matched without a manual
    dict conversion at every call site.
    """
    if not path:
        return None
    current: Any = data
    for segment in path.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
            continue
        if hasattr(current, segment):
            current = getattr(current, segment)
            continue
        return None
    if isinstance(current, Path):
        return str(current)
    return current
