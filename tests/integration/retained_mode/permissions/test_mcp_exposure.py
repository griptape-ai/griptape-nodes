"""Verify the permission-management request types are exposed as MCP tools.

The MCP server uses an explicit allowlist (`SUPPORTED_REQUEST_EVENTS`). These
tests pin the contract: every permission-management request type appears in
the allowlist and round-trips correctly through the same construction path
the MCP server uses (`SUPPORTED_REQUEST_EVENTS[name](**arguments)`).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

import griptape_nodes.retained_mode.managers.config_manager as config_manager_module
from griptape_nodes.retained_mode.events.permission_events import (
    GetEffectivePolicyRequest,
    GetEffectivePolicyResultSuccess,
    GrantPermissionRuleRequest,
    GrantPermissionRuleResultSuccess,
    ListPermissionDecisionsRequest,
    ListPermissionDecisionsResultSuccess,
    RevokePermissionRuleRequest,
    RevokePermissionRuleResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.servers.mcp import SUPPORTED_REQUEST_EVENTS
from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def permission_env() -> Generator[dict, None, None]:
    """Bring up an isolated GriptapeNodes singleton for round-trip tests."""
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
                    "permissions": {"enabled": True, "policy": {"rules": []}},
                }
            )
        )
        with patch.object(config_manager_module, "USER_CONFIG_PATH", config_path):
            GriptapeNodes()
            yield {}
        SingletonMeta._instances.clear()


class TestPermissionToolsExposed:
    """All four permission-management request types appear in the MCP allowlist."""

    def test_grant_permission_rule_request_is_exposed(self) -> None:
        assert SUPPORTED_REQUEST_EVENTS["GrantPermissionRuleRequest"] is GrantPermissionRuleRequest

    def test_revoke_permission_rule_request_is_exposed(self) -> None:
        assert SUPPORTED_REQUEST_EVENTS["RevokePermissionRuleRequest"] is RevokePermissionRuleRequest

    def test_get_effective_policy_request_is_exposed(self) -> None:
        assert SUPPORTED_REQUEST_EVENTS["GetEffectivePolicyRequest"] is GetEffectivePolicyRequest

    def test_list_permission_decisions_request_is_exposed(self) -> None:
        assert SUPPORTED_REQUEST_EVENTS["ListPermissionDecisionsRequest"] is ListPermissionDecisionsRequest


class TestPermissionToolsRoundTrip:
    """Each tool, called the way the MCP server calls it, produces a working result.

    This mirrors `mcp.py:call_tool`: look up the class, construct from a dict of
    arguments, dispatch through `GriptapeNodes.handle_request`. If the construction
    or dispatch shape changes, these tests fail before users hit it.
    """

    def test_grant_then_get_effective_policy(self, permission_env: dict) -> None:  # noqa: ARG002
        # Arguments shape mirrors what an MCP client would send.
        grant_args = {
            "rule": {
                "id": "mcp.grant-test",
                "decision": "allow",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        }
        grant_cls = SUPPORTED_REQUEST_EVENTS["GrantPermissionRuleRequest"]
        grant_result = GriptapeNodes.handle_request(grant_cls(**grant_args))
        assert isinstance(grant_result, GrantPermissionRuleResultSuccess)
        assert grant_result.rule_id == "mcp.grant-test"

        # GetEffectivePolicy also goes through the allowlist.
        get_cls = SUPPORTED_REQUEST_EVENTS["GetEffectivePolicyRequest"]
        get_result = GriptapeNodes.handle_request(get_cls())
        assert isinstance(get_result, GetEffectivePolicyResultSuccess)
        rule_ids = [r["id"] for r in get_result.policy["rules"]]
        assert "mcp.grant-test" in rule_ids

    def test_list_decisions(self, permission_env: dict) -> None:  # noqa: ARG002
        list_cls = SUPPORTED_REQUEST_EVENTS["ListPermissionDecisionsRequest"]
        result = GriptapeNodes.handle_request(list_cls(limit=5))
        assert isinstance(result, ListPermissionDecisionsResultSuccess)

    def test_revoke(self, permission_env: dict) -> None:  # noqa: ARG002
        grant_cls = SUPPORTED_REQUEST_EVENTS["GrantPermissionRuleRequest"]
        GriptapeNodes.handle_request(grant_cls(rule={"id": "mcp.revoke-target", "decision": "allow"}))
        revoke_cls = SUPPORTED_REQUEST_EVENTS["RevokePermissionRuleRequest"]
        revoke_result = GriptapeNodes.handle_request(revoke_cls(rule_id="mcp.revoke-target"))
        assert isinstance(revoke_result, RevokePermissionRuleResultSuccess)
