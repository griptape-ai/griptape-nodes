"""End-to-end tests for license-imposed policy that trumps user-set rules.

License rules live in a separate in-memory layer that's evaluated before user
rules. They're never persisted into user config, so a user editing
`griptape_nodes_config.json` cannot remove a license-imposed deny.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

import griptape_nodes.retained_mode.managers.config_manager as config_manager_module
from griptape_nodes.retained_mode.events.os_events import (
    ExistingFilePolicy,
    WriteFileRequest,
    WriteFileResultFailure,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.events.permission_events import (
    GetEffectivePolicyRequest,
    GetEffectivePolicyResultSuccess,
    GrantPermissionRuleRequest,
    GrantPermissionRuleResultSuccess,
    RevokePermissionRuleRequest,
    RevokePermissionRuleResultFailure,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.permissions import (
    Decision,
    PermissionPolicy,
    PermissionRule,
    WhenClause,
)
from griptape_nodes.retained_mode.managers.permissions.matchers import ActionMatch
from griptape_nodes.retained_mode.managers.permissions.schema import (
    EqualsExpr,
    GlobExpr,
)
from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def permission_env() -> Generator[dict, None, None]:
    """Bring up an isolated GriptapeNodes singleton with a clean permissions config."""
    SingletonMeta._instances.clear()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "griptape_nodes_config.json"
        workspace = tmp_path / "ws"
        workspace.mkdir()
        config_path.write_text(
            json.dumps(
                {
                    "workspace_directory": str(workspace),
                    "permissions": {
                        "enabled": True,
                        "policy": {"rules": [], "default_decision": "allow"},
                    },
                }
            )
        )
        with patch.object(config_manager_module, "USER_CONFIG_PATH", config_path):
            gn = GriptapeNodes()
            yield {
                "gn": gn,
                "permission_manager": gn.PermissionManager(),
                "workspace": workspace,
                "tmp": tmp_path,
                "config_path": config_path,
            }
        SingletonMeta._instances.clear()


def _grant_user_rule(rule: dict) -> str:
    result = GriptapeNodes.handle_request(GrantPermissionRuleRequest(rule=rule))
    assert isinstance(result, GrantPermissionRuleResultSuccess), result.result_details
    return result.rule_id


def _license_policy(*rules: PermissionRule) -> PermissionPolicy:
    return PermissionPolicy(rules=list(rules), default_decision=Decision.ALLOW)


class TestLicenseTrumpsUser:
    """A license rule that fires before any user rule wins."""

    def test_license_deny_overrides_user_allow(self, permission_env: dict) -> None:
        """User says allow-everything; license says deny-WriteFile. License wins."""
        pm = permission_env["permission_manager"]
        _grant_user_rule(
            {
                "id": "user.allow-anything",
                "decision": "allow",
                "when": {"action": {"request_type": {"op": "glob", "pattern": "*"}}},
            }
        )
        pm.set_license_policy(
            _license_policy(
                PermissionRule(
                    id="license.no-writes",
                    decision=Decision.DENY,
                    reason="this license forbids writes",
                    when=WhenClause(action=ActionMatch(request_type=EqualsExpr(value="WriteFileRequest"))),
                )
            )
        )
        target = permission_env["workspace"] / "blocked-by-license.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="hi",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultFailure)
        assert "license.no-writes" in str(result.result_details)
        assert not target.exists()

    def test_license_allow_overrides_user_deny(self, permission_env: dict) -> None:
        """User says deny-WriteFile; license says allow-WriteFile. License wins."""
        pm = permission_env["permission_manager"]
        _grant_user_rule(
            {
                "id": "user.deny-writes",
                "decision": "deny",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        )
        pm.set_license_policy(
            _license_policy(
                PermissionRule(
                    id="license.allow-writes",
                    decision=Decision.ALLOW,
                    when=WhenClause(action=ActionMatch(request_type=EqualsExpr(value="WriteFileRequest"))),
                )
            )
        )
        target = permission_env["workspace"] / "allowed-by-license.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="hi",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultSuccess), result.result_details
        assert target.read_text() == "hi"

    def test_license_silent_falls_through_to_user(self, permission_env: dict) -> None:
        """License has no rule for this action; user rules apply normally."""
        pm = permission_env["permission_manager"]
        _grant_user_rule(
            {
                "id": "user.deny-writes",
                "decision": "deny",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        )
        pm.set_license_policy(
            _license_policy(
                PermissionRule(
                    id="license.cares-about-something-else",
                    decision=Decision.ALLOW,
                    when=WhenClause(action=ActionMatch(request_type=EqualsExpr(value="ReadFileRequest"))),
                )
            )
        )
        target = permission_env["workspace"] / "user-deny.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="hi",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultFailure)
        # User's deny rule is what blocked it, not the license's allow.
        assert "user.deny-writes" in str(result.result_details)


class TestLicensePersistenceIsolation:
    """License rules must never round-trip through user config."""

    def test_license_rules_never_persist_to_user_config(self, permission_env: dict) -> None:
        pm = permission_env["permission_manager"]
        pm.set_license_policy(
            _license_policy(
                PermissionRule(
                    id="license.no-writes",
                    decision=Decision.DENY,
                    when=WhenClause(action=ActionMatch(request_type=EqualsExpr(value="WriteFileRequest"))),
                )
            )
        )
        # Trigger a persist by issuing a user grant.
        _grant_user_rule(
            {
                "id": "user.something",
                "decision": "allow",
                "when": {"action": {"request_type": {"op": "glob", "pattern": "*"}}},
            }
        )
        # Read the on-disk user config: must not contain the license rule id.
        on_disk = json.loads(permission_env["config_path"].read_text())
        rule_ids = [r["id"] for r in on_disk["permissions"]["policy"]["rules"]]
        assert "user.something" in rule_ids
        assert "license.no-writes" not in rule_ids

    def test_user_grant_does_not_drop_license_rules(self, permission_env: dict) -> None:
        """A user adding a rule must not remove license rules from the live policy."""
        pm = permission_env["permission_manager"]
        pm.set_license_policy(
            _license_policy(
                PermissionRule(
                    id="license.locked",
                    decision=Decision.DENY,
                    when=WhenClause(action=ActionMatch(request_type=GlobExpr(pattern="Forbidden*"))),
                )
            )
        )
        _grant_user_rule(
            {
                "id": "user.something",
                "decision": "allow",
                "when": {"action": {"request_type": {"op": "glob", "pattern": "*"}}},
            }
        )
        license_rule_ids = [r.id for r in pm.license_policy.rules]
        assert "license.locked" in license_rule_ids

    def test_revoke_cannot_remove_license_rules(self, permission_env: dict) -> None:
        """RevokePermissionRuleRequest only operates on user rules."""
        pm = permission_env["permission_manager"]
        pm.set_license_policy(
            _license_policy(
                PermissionRule(
                    id="license.locked",
                    decision=Decision.DENY,
                    when=WhenClause(action=ActionMatch(request_type=EqualsExpr(value="WriteFileRequest"))),
                )
            )
        )
        # Attempt to revoke the license rule via the public API.
        result = GriptapeNodes.handle_request(RevokePermissionRuleRequest(rule_id="license.locked"))
        assert isinstance(result, RevokePermissionRuleResultFailure)
        # And the rule is still active.
        assert any(r.id == "license.locked" for r in pm.license_policy.rules)

    def test_clear_license_policy_drops_only_license_rules(self, permission_env: dict) -> None:
        pm = permission_env["permission_manager"]
        _grant_user_rule(
            {
                "id": "user.keep-me",
                "decision": "allow",
                "when": {"action": {"request_type": {"op": "glob", "pattern": "*"}}},
            }
        )
        pm.set_license_policy(
            _license_policy(
                PermissionRule(
                    id="license.transient",
                    decision=Decision.DENY,
                    when=WhenClause(action=ActionMatch(request_type=EqualsExpr(value="WriteFileRequest"))),
                )
            )
        )
        pm.clear_license_policy()
        assert pm.license_policy.rules == []
        assert any(r.id == "user.keep-me" for r in pm.user_policy.rules)


class TestLicenseAuditTrail:
    """Decisions stamped with the originating layer via `granted_by`."""

    def test_license_rules_auto_stamp_granted_by(self, permission_env: dict) -> None:
        pm = permission_env["permission_manager"]
        pm.set_license_policy(
            _license_policy(
                PermissionRule(
                    id="license.unstamped",
                    decision=Decision.DENY,
                    when=WhenClause(action=ActionMatch(request_type=GlobExpr(pattern="*"))),
                )
            )
        )
        active = pm.license_policy.rules[0]
        assert active.granted_by == "license"

    def test_caller_supplied_granted_by_is_preserved(self, permission_env: dict) -> None:
        pm = permission_env["permission_manager"]
        pm.set_license_policy(
            _license_policy(
                PermissionRule(
                    id="license.tagged",
                    decision=Decision.DENY,
                    granted_by="license:enterprise@2026.05",
                    when=WhenClause(action=ActionMatch(request_type=GlobExpr(pattern="*"))),
                )
            )
        )
        active = pm.license_policy.rules[0]
        assert active.granted_by == "license:enterprise@2026.05"


class TestEffectivePolicyView:
    """`GetEffectivePolicyRequest` returns the merged view in evaluation order."""

    def test_merged_view_lists_license_rules_first(self, permission_env: dict) -> None:
        pm = permission_env["permission_manager"]
        _grant_user_rule(
            {
                "id": "user.one",
                "decision": "allow",
                "when": {"action": {"request_type": {"op": "glob", "pattern": "*"}}},
            }
        )
        pm.set_license_policy(
            _license_policy(
                PermissionRule(
                    id="license.first",
                    decision=Decision.DENY,
                    when=WhenClause(action=ActionMatch(request_type=GlobExpr(pattern="*"))),
                )
            )
        )
        result = GriptapeNodes.handle_request(GetEffectivePolicyRequest())
        assert isinstance(result, GetEffectivePolicyResultSuccess)
        rule_ids = [r["id"] for r in result.policy["rules"]]
        # License rules come first in the merged view.
        assert rule_ids == ["license.first", "user.one"]
