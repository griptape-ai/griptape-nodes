"""Built-in fact providers shipped by PermissionManager.

`workspace.path`, `engine.id`, `loaded_libraries.names`, and `current_node.*`
are documented in `docs/permissions.md` and must round-trip with the docs.
These tests pin the contract: presence, shape, and invalidation behaviour.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

import griptape_nodes.retained_mode.managers.config_manager as config_manager_module
from griptape_nodes.retained_mode.events.permission_events import GrantPermissionRuleRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
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
            yield {"gn": gn, "workspace": workspace}
        SingletonMeta._instances.clear()


class TestBuiltinFactPresence:
    """Every documented built-in fact appears in the tree."""

    def test_all_documented_facts_present(self, permission_env: dict) -> None:
        pm = permission_env["gn"].PermissionManager()
        tree = pm.facts.build_fact_tree()
        # Workspace
        assert "workspace" in tree
        assert isinstance(tree["workspace"]["path"], str)
        assert tree["workspace"]["path"].endswith("ws")
        # Engine
        assert "engine" in tree
        assert tree["engine"]["id"] is None or isinstance(tree["engine"]["id"], str)
        # Loaded libraries
        assert "loaded_libraries" in tree
        assert isinstance(tree["loaded_libraries"]["names"], list)
        # Current node (None outside a push_principal block)
        assert "current_node" in tree
        assert tree["current_node"] == {
            "library": None,
            "node_type": None,
            "node_name": None,
        }


class TestBuiltinFactInvalidation:
    """Cached facts refresh in response to the right events."""

    def test_current_node_updates_with_push_principal(self, permission_env: dict) -> None:
        pm = permission_env["gn"].PermissionManager()
        pm.push_principal(library="lib-a", node_type="NodeT", node_name="n1")
        try:
            tree = pm.facts.build_fact_tree()
        finally:
            pm.pop_principal()
        assert tree["current_node"] == {
            "library": "lib-a",
            "node_type": "NodeT",
            "node_name": "n1",
        }
        cleared = pm.facts.build_fact_tree()
        assert cleared["current_node"]["library"] is None


class TestRuleAgainstBuiltinFact:
    """A real rule using a built-in fact path fires correctly via the dispatcher."""

    def test_engine_principal_blocked_when_in_node_context(self, permission_env: dict) -> None:
        from griptape_nodes.retained_mode.events.os_events import (
            ExistingFilePolicy,
            WriteFileRequest,
            WriteFileResultFailure,
            WriteFileResultSuccess,
        )

        gn = permission_env["gn"]
        pm = gn.PermissionManager()

        # Rule: deny WriteFileRequest while a node from "untrusted-lib" is on top.
        GriptapeNodes.handle_request(
            GrantPermissionRuleRequest(
                rule={
                    "id": "user.deny-untrusted-node-writes",
                    "decision": "deny",
                    "when": {
                        "action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}},
                        "context": {"facts": {"current_node.library": {"op": "equals", "value": "untrusted-lib"}}},
                    },
                }
            )
        )
        target = permission_env["workspace"] / "ok.txt"
        # Outside any node context: rule does not fire.
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="hi",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultSuccess)
        # Inside a matching node context: rule fires.
        pm.push_principal(library="untrusted-lib", node_type="X", node_name="x1")
        try:
            target2 = permission_env["workspace"] / "blocked.txt"
            result2 = GriptapeNodes.handle_request(
                WriteFileRequest(
                    file_path=str(target2),
                    content="hi",
                    existing_file_policy=ExistingFilePolicy.OVERWRITE,
                )
            )
        finally:
            pm.pop_principal()
        assert isinstance(result2, WriteFileResultFailure)
        assert "user.deny-untrusted-node-writes" in str(result2.result_details)
