"""Unit tests for the permission match expression schema and matcher engine."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from griptape_nodes.retained_mode.managers.permissions import (
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
    Principal,
    PrincipalKind,
    PrincipalMatch,
    ResourceMatch,
    WhenClause,
    evaluate_policy,
    evaluate_rule,
)
from griptape_nodes.retained_mode.managers.permissions.matchers import ActionMatch


class TestMatchExprPrimitives:
    """Each operator should match what its docstring claims and nothing else."""

    def test_equals(self) -> None:
        rule = _rule_with_resource("name", EqualsExpr(value="foo"))
        assert evaluate_rule(rule, **_ctx(request_fields={"name": "foo"}))
        assert not evaluate_rule(rule, **_ctx(request_fields={"name": "bar"}))

    def test_in(self) -> None:
        rule = _rule_with_resource("color", InExpr(values=["red", "green"]))
        assert evaluate_rule(rule, **_ctx(request_fields={"color": "red"}))
        assert not evaluate_rule(rule, **_ctx(request_fields={"color": "blue"}))

    def test_in_against_list_field_uses_any_overlap(self) -> None:
        rule = _rule_with_resource("tags", InExpr(values=["security", "infra"]))
        assert evaluate_rule(rule, **_ctx(request_fields={"tags": ["security"]}))
        assert evaluate_rule(rule, **_ctx(request_fields={"tags": ["random", "infra"]}))
        assert not evaluate_rule(rule, **_ctx(request_fields={"tags": ["random"]}))

    def test_glob(self) -> None:
        rule = _rule_with_resource("name", GlobExpr(pattern="prefix_*"))
        assert evaluate_rule(rule, **_ctx(request_fields={"name": "prefix_thing"}))
        assert not evaluate_rule(rule, **_ctx(request_fields={"name": "thing"}))

    def test_not(self) -> None:
        rule = _rule_with_resource("name", NotExpr(expr=EqualsExpr(value="foo")))
        assert not evaluate_rule(rule, **_ctx(request_fields={"name": "foo"}))
        assert evaluate_rule(rule, **_ctx(request_fields={"name": "bar"}))

    def test_all_of(self) -> None:
        rule = _rule_with_resource("name", AllOfExpr(exprs=[GlobExpr(pattern="a*"), GlobExpr(pattern="*z")]))
        assert evaluate_rule(rule, **_ctx(request_fields={"name": "a-foo-z"}))
        assert not evaluate_rule(rule, **_ctx(request_fields={"name": "a-foo"}))

    def test_any_of(self) -> None:
        rule = _rule_with_resource("name", AnyOfExpr(exprs=[EqualsExpr(value="foo"), EqualsExpr(value="bar")]))
        assert evaluate_rule(rule, **_ctx(request_fields={"name": "foo"}))
        assert evaluate_rule(rule, **_ctx(request_fields={"name": "bar"}))
        assert not evaluate_rule(rule, **_ctx(request_fields={"name": "baz"}))


class TestPathUnderExpr:
    """`path_under` does macro expansion + canonical containment, not string prefix match."""

    @pytest.fixture
    def workspace(self) -> Path:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            yield ws

    def test_inside(self, workspace: Path) -> None:
        rule = _rule_with_resource("file_path", PathUnderExpr(root="${workspace}"))
        target = workspace / "outputs" / "image.png"
        assert evaluate_rule(
            rule,
            **_ctx(request_fields={"file_path": str(target)}, macros={"workspace": str(workspace)}),
        )

    def test_outside(self, workspace: Path) -> None:
        rule = _rule_with_resource("file_path", PathUnderExpr(root="${workspace}"))
        target = workspace.parent / "elsewhere.png"
        assert not evaluate_rule(
            rule,
            **_ctx(request_fields={"file_path": str(target)}, macros={"workspace": str(workspace)}),
        )

    def test_none_value(self, workspace: Path) -> None:
        rule = _rule_with_resource("file_path", PathUnderExpr(root="${workspace}"))
        assert not evaluate_rule(
            rule,
            **_ctx(request_fields={"file_path": None}, macros={"workspace": str(workspace)}),
        )


class TestPrincipalMatch:
    """The principal axis matches kind first, then optional library/node_type/topic predicates."""

    def test_kind_filter(self) -> None:
        rule = _rule_with(
            principal=PrincipalMatch(kind=[PrincipalKind.NODE]),
        )
        assert evaluate_rule(
            rule,
            **_ctx(principal=Principal(kind=PrincipalKind.NODE, library="lib", node_type="T")),
        )
        assert not evaluate_rule(rule, **_ctx(principal=Principal(kind=PrincipalKind.ENGINE)))

    def test_library_predicate(self) -> None:
        rule = _rule_with(
            principal=PrincipalMatch(
                kind=[PrincipalKind.NODE],
                library=EqualsExpr(value="my-lib"),
            ),
        )
        assert evaluate_rule(
            rule,
            **_ctx(principal=Principal(kind=PrincipalKind.NODE, library="my-lib", node_type="T")),
        )
        assert not evaluate_rule(
            rule,
            **_ctx(principal=Principal(kind=PrincipalKind.NODE, library="other-lib", node_type="T")),
        )


class TestActionAndContext:
    def test_action_request_type_match(self) -> None:
        rule = _rule_with(action=ActionMatch(request_type=EqualsExpr(value="WriteFileRequest")))
        assert evaluate_rule(rule, **_ctx(request_type_name="WriteFileRequest"))
        assert not evaluate_rule(rule, **_ctx(request_type_name="ReadFileRequest"))

    def test_context_dot_path(self) -> None:
        rule = _rule_with(
            context=ContextMatch(facts={"loaded_libraries.names": InExpr(values=["lib-a"])}),
        )
        assert evaluate_rule(
            rule,
            **_ctx(facts={"loaded_libraries": {"names": ["lib-a", "lib-b"]}}),
        )
        assert not evaluate_rule(
            rule,
            **_ctx(facts={"loaded_libraries": {"names": ["lib-x"]}}),
        )


class TestInspectedValues:
    """`EvaluationResult.inspected_values` carries the field=value pairs the matching rule consulted."""

    def test_resource_values_captured_on_match(self) -> None:
        rule = _rule_with(
            action=ActionMatch(request_type=EqualsExpr(value="WriteFileRequest")),
            resource=ResourceMatch(fields={"file_path": NotExpr(expr=GlobExpr(pattern="/ws/*"))}),
        )
        policy = PermissionPolicy(
            rules=[
                PermissionRule(id="deny-outside", decision=Decision.DENY, when=rule.when),
            ]
        )
        result = evaluate_policy(
            policy,
            **_ctx(
                request_type_name="WriteFileRequest",
                request_fields={"file_path": "/var/elsewhere.txt"},
            ),
        )
        assert result.matched_rule is not None
        assert result.matched_rule.id == "deny-outside"
        assert result.inspected_values["resource.file_path"] == "/var/elsewhere.txt"
        assert result.inspected_values["action.request_type"] == "WriteFileRequest"

    def test_inspected_values_scoped_to_matching_rule(self) -> None:
        """Values from earlier non-matching rules do not bleed into the matching rule's map.

        `inspected_paths` deliberately accumulates across every rule the matcher
        walked, but `inspected_values` is reset per rule so the denial message
        only shows fields the matching rule actually evaluated.
        """
        policy = PermissionPolicy(
            rules=[
                PermissionRule(
                    id="miss",
                    decision=Decision.ALLOW,
                    when=WhenClause(resource=ResourceMatch(fields={"name": EqualsExpr(value="never")})),
                ),
                PermissionRule(
                    id="hit",
                    decision=Decision.DENY,
                    when=WhenClause(
                        resource=ResourceMatch(fields={"file_path": GlobExpr(pattern="*.txt")}),
                    ),
                ),
            ]
        )
        result = evaluate_policy(
            policy,
            **_ctx(
                request_fields={"name": "actual", "file_path": "/var/x.txt"},
            ),
        )
        assert result.matched_rule is not None
        assert result.matched_rule.id == "hit"
        assert "resource.file_path" in result.inspected_values
        assert result.inspected_values["resource.file_path"] == "/var/x.txt"
        # The miss rule inspected resource.name; its value must not survive.
        assert "resource.name" not in result.inspected_values
        # Inspected paths still carry the cross-rule trace for audit purposes.
        assert "resource.name" in result.inspected_paths
        assert "resource.file_path" in result.inspected_paths

    def test_default_fall_through_has_empty_values(self) -> None:
        policy = PermissionPolicy(default_decision=Decision.DENY)
        result = evaluate_policy(policy, **_ctx())
        assert result.matched_rule is None
        assert result.inspected_values == {}

    def test_context_values_captured(self) -> None:
        rule = _rule_with(
            context=ContextMatch(facts={"loaded_libraries.names": InExpr(values=["lib-x"])}),
        )
        policy = PermissionPolicy(
            rules=[PermissionRule(id="hit", decision=Decision.DENY, when=rule.when)],
        )
        result = evaluate_policy(
            policy,
            **_ctx(facts={"loaded_libraries": {"names": ["lib-x", "lib-y"]}}),
        )
        assert result.matched_rule is not None
        assert result.inspected_values["context.loaded_libraries.names"] == ["lib-x", "lib-y"]


class TestPolicyOrdering:
    """First-match-wins, with fall-through to default_decision."""

    def test_first_match_wins(self) -> None:
        policy = PermissionPolicy(
            rules=[
                PermissionRule(
                    id="allow-x",
                    decision=Decision.ALLOW,
                    when=WhenClause(
                        action=ActionMatch(request_type=EqualsExpr(value="X")),
                    ),
                ),
                PermissionRule(
                    id="deny-x",
                    decision=Decision.DENY,
                    when=WhenClause(
                        action=ActionMatch(request_type=EqualsExpr(value="X")),
                    ),
                ),
            ],
            default_decision=Decision.PROMPT,
        )
        result = evaluate_policy(policy, **_ctx(request_type_name="X"))
        assert result.decision is Decision.ALLOW
        assert result.matched_rule is not None
        assert result.matched_rule.id == "allow-x"

    def test_falls_through_to_default(self) -> None:
        policy = PermissionPolicy(
            rules=[
                PermissionRule(
                    id="allow-x",
                    decision=Decision.ALLOW,
                    when=WhenClause(action=ActionMatch(request_type=EqualsExpr(value="X"))),
                ),
            ],
            default_decision=Decision.DENY,
        )
        result = evaluate_policy(policy, **_ctx(request_type_name="Y"))
        assert result.decision is Decision.DENY
        assert result.matched_rule is None


# ---------------------------------------------------------------------- helpers


def _rule_with(**when_kwargs) -> PermissionRule:
    return PermissionRule(id="r", decision=Decision.ALLOW, when=WhenClause(**when_kwargs))


def _rule_with_resource(field_name: str, expr: MatchExpr) -> PermissionRule:
    return _rule_with(resource=ResourceMatch(fields={field_name: expr}))


def _ctx(
    *,
    principal: Principal | None = None,
    request_type_name: str = "TestRequest",
    request_fields: dict | None = None,
    facts: dict | None = None,
    macros: dict | None = None,
) -> dict:
    return {
        "principal": principal or Principal(kind=PrincipalKind.ENGINE),
        "request_type_name": request_type_name,
        "request_fields": request_fields or {},
        "facts": facts or {},
        "macro_context": macros or {},
    }
