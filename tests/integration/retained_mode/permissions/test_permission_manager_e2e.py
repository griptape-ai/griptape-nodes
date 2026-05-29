"""End-to-end tests for the permission system.

These tests run the full request dispatcher (`GriptapeNodes.handle_request`)
with a `PermissionManager` enforcing policy via the pre-dispatch hook. They
exercise the worked-policy examples from the design doc end to end.
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
    FileIOFailureReason,
    ListDirectoryRequest,
    ReadFileRequest,
    WriteFileRequest,
    WriteFileResultFailure,
    WriteFileResultSuccess,
)
from griptape_nodes.retained_mode.events.permission_events import (
    GetEffectivePolicyRequest,
    GetEffectivePolicyResultSuccess,
    GrantPermissionRuleRequest,
    GrantPermissionRuleResultFailure,
    GrantPermissionRuleResultSuccess,
    ListPermissionDecisionsRequest,
    ListPermissionDecisionsResultSuccess,
    PermissionDecisionEvent,
    RevokePermissionRuleRequest,
    RevokePermissionRuleResultFailure,
    RevokePermissionRuleResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.permissions import (
    Decision,
)
from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from collections.abc import Generator

_EXPECTED_THREE = 3

# ----------------------------------------------------------------------- fixtures


@pytest.fixture
def permission_env() -> Generator[dict, None, None]:
    """Bring up an isolated GriptapeNodes singleton + workspace + permissions config.

    Sets workspace through the real config setter so set_config_value calls in
    tests don't reset workspace_path back to the default.
    """
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
                        "consent_prompts_enabled": True,
                        "audit_log_max_entries": 100,
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


# ----------------------------------------------------------------------- helpers


def _grant(rule: dict) -> str:
    result = GriptapeNodes.handle_request(GrantPermissionRuleRequest(rule=rule))
    assert isinstance(result, GrantPermissionRuleResultSuccess), result.result_details
    return result.rule_id


# ----------------------------------------------------------------------- tests


class TestEnforcedDispatch:
    """The dispatcher hook denies, allows, and short-circuits with typed failures."""

    def test_engine_default_allow_passes_through(self, permission_env: dict) -> None:
        """With default_decision=allow and no rules, requests succeed normally."""
        target = permission_env["workspace"] / "out.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="hello",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultSuccess), result.result_details
        assert target.read_text() == "hello"

    def test_deny_rule_short_circuits_with_typed_failure(self, permission_env: dict) -> None:
        """A matching deny rule returns the request's typed failure with PERMISSION_DENIED."""
        _grant(
            {
                "id": "deny-all-writes",
                "decision": "deny",
                "reason": "writes are blocked in this test",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        )
        target = permission_env["workspace"] / "blocked.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="nope",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason is FileIOFailureReason.PERMISSION_DENIED
        assert "deny-all-writes" in str(result.result_details)
        assert not target.exists()

    def test_allow_rule_lets_request_through(self, permission_env: dict) -> None:
        """An earlier allow rule beats a later catch-all deny."""
        _grant(
            {
                "id": "allow-workspace-write",
                "decision": "allow",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}},
                    "resource": {"fields": {"file_path": {"op": "path_under", "root": "${workspace}"}}},
                },
            }
        )
        _grant(
            {
                "id": "deny-everything-else",
                "decision": "deny",
                "when": {"action": {"request_type": {"op": "glob", "pattern": "*"}}},
            }
        )
        inside = permission_env["workspace"] / "ok.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(inside),
                content="hi",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultSuccess), result.result_details
        assert inside.read_text() == "hi"

    def test_path_under_denies_writes_outside_workspace(self, permission_env: dict) -> None:
        """`path_under` distinguishes writes inside vs outside the workspace."""
        _grant(
            {
                "id": "allow-workspace-write",
                "decision": "allow",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}},
                    "resource": {"fields": {"file_path": {"op": "path_under", "root": "${workspace}"}}},
                },
            }
        )
        _grant(
            {
                "id": "deny-non-workspace-writes",
                "decision": "deny",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        )
        outside = permission_env["tmp"] / "elsewhere.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(outside),
                content="hi",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultFailure)
        assert result.failure_reason is FileIOFailureReason.PERMISSION_DENIED
        assert not outside.exists()

    def test_denial_message_includes_inspected_field_value(self, permission_env: dict) -> None:
        """Denial messages name the field=value the matching rule consulted.

        Surfacing the resolved value lets callers see *why* a request was
        blocked (e.g. "file_path=/tmp/elsewhere.txt") without diving into the
        audit log or re-running the matcher.
        """
        _grant(
            {
                "id": "deny-outside-workspace",
                "decision": "deny",
                "reason": "writes outside the workspace are blocked",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}},
                    "resource": {
                        "fields": {
                            "file_path": {"op": "not", "expr": {"op": "path_under", "root": "${workspace}"}},
                        }
                    },
                },
            }
        )
        outside = permission_env["tmp"] / "elsewhere.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(outside),
                content="nope",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultFailure)
        details = str(result.result_details)
        assert "deny-outside-workspace" in details
        assert "writes outside the workspace are blocked" in details
        assert f"resource.file_path={outside}" in details
        assert not outside.exists()

    def test_read_only_requests_unaffected_by_write_deny(self, permission_env: dict) -> None:
        """A WriteFileRequest-targeted deny does not block ReadFileRequest."""
        target = permission_env["workspace"] / "input.txt"
        target.write_text("abc")
        _grant(
            {
                "id": "deny-writes",
                "decision": "deny",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        )
        result = GriptapeNodes.handle_request(ReadFileRequest(file_path=str(target)))
        # Read should succeed (we're only denying writes).
        assert result.succeeded(), result.result_details

    def test_list_directory_unaffected(self, permission_env: dict) -> None:
        _grant(
            {
                "id": "deny-writes",
                "decision": "deny",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        )
        result = GriptapeNodes.handle_request(ListDirectoryRequest(directory_path=str(permission_env["workspace"])))
        assert result.succeeded()


class TestPrincipalAxis:
    """`PrincipalKind` matching: engine, node, client."""

    def test_node_principal_passes_when_library_matches(self, permission_env: dict) -> None:
        """While `push_principal` is active, the actor presents as `node:<lib>/<type>`."""
        pm = permission_env["permission_manager"]
        _grant(
            {
                "id": "allow-when-image-lib",
                "decision": "allow",
                "when": {
                    "principal": {
                        "kind": ["node"],
                        "library": {"op": "equals", "value": "advanced-image-library"},
                    },
                    "action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}},
                },
            }
        )
        _grant(
            {
                "id": "deny-everything-else-w",
                "decision": "deny",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        )
        target = permission_env["workspace"] / "node-output.txt"

        # Without principal: denied
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="x",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultFailure)

        # With matching node principal: allowed
        pm.push_principal(library="advanced-image-library", node_type="UpscaleNode", node_name="up_1")
        try:
            result = GriptapeNodes.handle_request(
                WriteFileRequest(
                    file_path=str(target),
                    content="x",
                    existing_file_policy=ExistingFilePolicy.OVERWRITE,
                )
            )
        finally:
            pm.pop_principal()
        assert isinstance(result, WriteFileResultSuccess), result.result_details
        assert target.read_text() == "x"

    def test_node_principal_with_wrong_library_still_denied(self, permission_env: dict) -> None:
        pm = permission_env["permission_manager"]
        _grant(
            {
                "id": "allow-only-image-lib",
                "decision": "allow",
                "when": {
                    "principal": {
                        "kind": ["node"],
                        "library": {"op": "equals", "value": "advanced-image-library"},
                    },
                    "action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}},
                },
            }
        )
        _grant(
            {
                "id": "deny-other-writes",
                "decision": "deny",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        )
        target = permission_env["workspace"] / "x.txt"
        pm.push_principal(library="other-library", node_type="OtherNode", node_name="o_1")
        try:
            result = GriptapeNodes.handle_request(
                WriteFileRequest(
                    file_path=str(target),
                    content="x",
                    existing_file_policy=ExistingFilePolicy.OVERWRITE,
                )
            )
        finally:
            pm.pop_principal()
        assert isinstance(result, WriteFileResultFailure)


class TestContextFactsAndEnrichers:
    """Rules that match against the fact tree (loaded libraries, request enrichers)."""

    def test_loaded_libraries_provider_drives_context_match(self, permission_env: dict) -> None:
        pm = permission_env["permission_manager"]
        loaded = ["lib-a"]
        pm.facts.register_provider("loaded_libraries.names", lambda: list(loaded))
        _grant(
            {
                "id": "deny-when-lib-a-loaded",
                "decision": "deny",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}},
                    "context": {"facts": {"loaded_libraries.names": {"op": "in", "values": ["lib-a"]}}},
                },
            }
        )
        target = permission_env["workspace"] / "y.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="x",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultFailure)
        loaded.clear()
        loaded.append("lib-z")
        # Force a re-read of the fact (provider is PER_REQUEST by default)
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="x",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultSuccess), result.result_details

    def test_request_enricher_publishes_per_request_facts(self, permission_env: dict) -> None:
        """A manager can publish facts derived from the request being evaluated."""
        pm = permission_env["permission_manager"]

        def enricher(request: WriteFileRequest) -> dict:
            return {"content_kind": "binary" if isinstance(request.content, bytes) else "text"}

        pm.facts.register_request_enricher(WriteFileRequest.__name__, enricher)
        _grant(
            {
                "id": "deny-binary-writes",
                "decision": "deny",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}},
                    "context": {"facts": {"request.content_kind": {"op": "equals", "value": "binary"}}},
                },
            }
        )
        # Text write: allowed (default_decision=allow, no matching rule)
        text_target = permission_env["workspace"] / "text.txt"
        text_result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(text_target),
                content="hi",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(text_result, WriteFileResultSuccess), text_result.result_details

        # Binary write: blocked by the enricher-driven rule
        bin_target = permission_env["workspace"] / "bin.bin"
        bin_result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(bin_target),
                content=b"\x00\x01\x02",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(bin_result, WriteFileResultFailure)
        assert not bin_target.exists()


class TestAuditAndDecisionEvents:
    """The audit ring buffer and `PermissionDecisionEvent` carry the same data."""

    def test_decisions_appear_in_ring_buffer(self, permission_env: dict) -> None:
        _grant(
            {
                "id": "deny-everything",
                "decision": "deny",
                "when": {"action": {"request_type": {"op": "glob", "pattern": "*"}}},
            }
        )
        target = permission_env["workspace"] / "z.txt"
        for _ in range(3):
            GriptapeNodes.handle_request(
                WriteFileRequest(
                    file_path=str(target),
                    content="z",
                    existing_file_policy=ExistingFilePolicy.OVERWRITE,
                )
            )
        result = GriptapeNodes.handle_request(ListPermissionDecisionsRequest(limit=10))
        assert isinstance(result, ListPermissionDecisionsResultSuccess)
        write_decisions = [d for d in result.decisions if d["action_request_type"] == "WriteFileRequest"]
        assert len(write_decisions) == _EXPECTED_THREE
        for entry in write_decisions:
            assert entry["decision"] == Decision.DENY.value
            assert entry["rule_id"] == "deny-everything"
            assert "action.request_type" in entry["inspected_paths"]
        assert len(write_decisions) == _EXPECTED_THREE

    def test_decision_event_broadcast(self, permission_env: dict) -> None:
        gn = permission_env["gn"]
        events: list[PermissionDecisionEvent] = []
        gn.EventManager().add_listener_to_app_event(PermissionDecisionEvent, events.append)
        _grant(
            {
                "id": "deny-writes-evt",
                "decision": "deny",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        )
        target = permission_env["workspace"] / "ev.txt"
        GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="hi",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        write_events = [e for e in events if e.action_request_type == "WriteFileRequest"]
        assert any(e.decision == Decision.DENY.value and e.rule_id == "deny-writes-evt" for e in write_events)


class TestPolicyManagementRequests:
    """Grant / revoke / read-effective-policy round-trip through the dispatcher.

    These requests are exempt from the hook so a too-restrictive policy can
    always be repaired.
    """

    def test_grant_accepts_well_formed_rule(self, permission_env: dict) -> None:  # noqa: ARG002
        rid = _grant(
            {
                "id": "ok-rule",
                "decision": "allow",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        )
        assert rid == "ok-rule"

    def test_grant_rejects_invalid_operator(self, permission_env: dict) -> None:  # noqa: ARG002
        result = GriptapeNodes.handle_request(
            GrantPermissionRuleRequest(
                rule={
                    "id": "bad",
                    "decision": "allow",
                    "when": {"action": {"request_type": {"op": "regex", "pattern": ".*"}}},
                }
            )
        )
        assert isinstance(result, GrantPermissionRuleResultFailure)

    def test_revoke_removes_rule_and_no_op_failure_otherwise(self, permission_env: dict) -> None:  # noqa: ARG002
        _grant(
            {
                "id": "to-remove",
                "decision": "deny",
                "when": {"action": {"request_type": {"op": "glob", "pattern": "*"}}},
            }
        )
        revoke = GriptapeNodes.handle_request(RevokePermissionRuleRequest(rule_id="to-remove"))
        assert isinstance(revoke, RevokePermissionRuleResultSuccess)
        # Second revoke is a no-op failure with a clear reason.
        again = GriptapeNodes.handle_request(RevokePermissionRuleRequest(rule_id="to-remove"))
        assert isinstance(again, RevokePermissionRuleResultFailure)

    def test_get_effective_policy_returns_active_rules(self, permission_env: dict) -> None:  # noqa: ARG002
        _grant({"id": "one", "decision": "allow", "when": {}})
        _grant({"id": "two", "decision": "deny", "when": {}})
        result = GriptapeNodes.handle_request(GetEffectivePolicyRequest())
        assert isinstance(result, GetEffectivePolicyResultSuccess)
        rule_ids = [r["id"] for r in result.policy["rules"]]
        assert rule_ids == ["one", "two"]


class TestWorkedExampleFromDesignDoc:
    """Reproduce the merged-policy example given in the design doc end to end."""

    def _install_worked_example(self) -> None:
        for rule in [
            {
                "id": "engine-default.read-anywhere",
                "granted_by": "engine-default",
                "decision": "allow",
                "when": {
                    "action": {
                        "request_type": {
                            "op": "in",
                            "values": [
                                "ReadFileRequest",
                                "GetFileInfoRequest",
                                "ListDirectoryRequest",
                            ],
                        }
                    }
                },
            },
            {
                "id": "engine-default.write-under-workspace",
                "granted_by": "engine-default",
                "decision": "allow",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}},
                    "resource": {"fields": {"file_path": {"op": "path_under", "root": "${workspace}"}}},
                },
            },
            {
                "id": "engine-default.deny-arbitrary-python-from-clients",
                "granted_by": "engine-default",
                "decision": "deny",
                "reason": "Arbitrary Python execution from external clients is disabled by default.",
                "when": {
                    "principal": {"kind": ["client"]},
                    "action": {
                        "request_type": {
                            "op": "equals",
                            "value": "RunArbitraryPythonStringRequest",
                        }
                    },
                },
            },
            {
                "id": "user.allow-image-lib-write-outputs",
                "granted_by": "user",
                "decision": "allow",
                "when": {
                    "principal": {
                        "kind": ["node"],
                        "library": {"op": "equals", "value": "advanced-image-library"},
                    },
                    "action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}},
                    "resource": {"fields": {"file_path": {"op": "path_under", "root": "${workspace}/outputs"}}},
                },
            },
            {
                "id": "user.deny-labs-stage-libraries",
                "granted_by": "user",
                "decision": "deny",
                "reason": "Labs-stage libraries are not permitted in this workspace.",
                "when": {
                    "action": {
                        "request_type": {
                            "op": "equals",
                            "value": "RegisterLibraryFromFileRequest",
                        }
                    },
                    "context": {
                        "facts": {
                            "request.metadata.declarations.lifecycle_stage": {
                                "op": "equals",
                                "value": "LABS",
                            }
                        }
                    },
                },
            },
        ]:
            _grant(rule)

    def test_engine_defaults_block_writes_outside_workspace(self, permission_env: dict) -> None:
        # Tighten default to deny so engine-default rules are the only allow path.
        permission_env["permission_manager"]._user_policy.default_decision = Decision.DENY
        self._install_worked_example()
        outside = permission_env["tmp"] / "elsewhere.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(outside),
                content="hi",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultFailure)
        assert not outside.exists()

    def test_engine_defaults_allow_writes_under_workspace(self, permission_env: dict) -> None:
        permission_env["permission_manager"]._user_policy.default_decision = Decision.DENY
        self._install_worked_example()
        target = permission_env["workspace"] / "out.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="hi",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultSuccess), result.result_details

    def test_image_lib_node_writes_to_outputs_subdir(self, permission_env: dict) -> None:
        permission_env["permission_manager"]._user_policy.default_decision = Decision.DENY
        self._install_worked_example()
        outputs_dir = permission_env["workspace"] / "outputs"
        outputs_dir.mkdir()
        target = outputs_dir / "render.png"
        pm = permission_env["permission_manager"]
        pm.push_principal(library="advanced-image-library", node_type="UpscaleNode", node_name="u1")
        try:
            result = GriptapeNodes.handle_request(
                WriteFileRequest(
                    file_path=str(target),
                    content=b"\x89PNG",
                    existing_file_policy=ExistingFilePolicy.OVERWRITE,
                )
            )
        finally:
            pm.pop_principal()
        assert isinstance(result, WriteFileResultSuccess), result.result_details

    def test_labs_lifecycle_blocks_register_library(self, permission_env: dict) -> None:
        """Use a request enricher to publish parsed declarations and gate registration."""
        permission_env["permission_manager"]._user_policy.default_decision = Decision.DENY
        self._install_worked_example()
        pm = permission_env["permission_manager"]
        # Stand-in for what LibraryManager will eventually publish: parsed
        # declarations of the library being registered, namespaced under
        # request.metadata.declarations.
        pm.facts.register_request_enricher(
            "RegisterLibraryFromFileRequest",
            lambda _: {"metadata.declarations.lifecycle_stage": "LABS"},
        )
        # Allow the registration request type so only the labs rule can deny.
        _grant(
            {
                "id": "engine-default.allow-register",
                "decision": "allow",
                "when": {
                    "action": {
                        "request_type": {
                            "op": "equals",
                            "value": "RegisterLibraryFromFileRequest",
                        }
                    }
                },
            }
        )
        from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest

        result = GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path="/nonexistent.json"))
        # The denial happens at the dispatcher hook before the library manager
        # ever sees the request, so the failure carries our deny reason rather
        # than a "file not found" reason.
        assert not result.succeeded()
        assert "labs-stage" in str(result.result_details).lower() or "LABS" in str(result.result_details)


class TestLayeredConfig:
    """Per-layer reading: project / workspace / env contribute rules ahead of user."""

    @staticmethod
    def _install_workspace_permissions(permission_env: dict, block: dict) -> None:
        """Write a workspace `griptape_nodes_config.json` and reload.

        Goes through `cm.load_workspace_config` so the layer survives any
        subsequent `cm.load_configs()` triggered by config writes elsewhere.
        """
        workspace = permission_env["workspace"]
        (workspace / "griptape_nodes_config.json").write_text(json.dumps({"permissions": block}))
        cm = permission_env["permission_manager"]._config_manager
        cm.load_workspace_config(workspace)
        permission_env["permission_manager"].reload()

    def test_workspace_layer_rule_fires_ahead_of_user_layer(self, permission_env: dict) -> None:
        """A workspace-layer deny beats a user-layer allow under first-match-wins."""
        # User's allow-everything rule is loaded first via the public grant API
        # so it lives in the user layer specifically.
        _grant(
            {
                "id": "user.allow-writes",
                "decision": "allow",
                "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
            }
        )
        # Workspace is higher-priority than user; its deny should fire first.
        self._install_workspace_permissions(
            permission_env,
            {
                "policy": {
                    "rules": [
                        {
                            "id": "workspace.deny-writes",
                            "decision": "deny",
                            "reason": "studio policy: writes blocked at workspace layer",
                            "when": {"action": {"request_type": {"op": "equals", "value": "WriteFileRequest"}}},
                        }
                    ]
                }
            },
        )

        target = permission_env["workspace"] / "blocked.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(target),
                content="nope",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        assert isinstance(result, WriteFileResultFailure)
        assert "workspace.deny-writes" in str(result.result_details)
        assert not target.exists()

    def test_workspace_layer_rules_auto_stamp_granted_by(self, permission_env: dict) -> None:
        """Rules loaded from a config layer get `granted_by` stamped with the layer name."""
        self._install_workspace_permissions(
            permission_env,
            {
                "policy": {
                    "rules": [
                        {
                            "id": "workspace.tag-me",
                            "decision": "deny",
                            "when": {"action": {"request_type": {"op": "glob", "pattern": "*"}}},
                        }
                    ]
                }
            },
        )

        result = GriptapeNodes.handle_request(GetEffectivePolicyRequest())
        assert isinstance(result, GetEffectivePolicyResultSuccess)
        rules = result.policy["rules"]
        match = next(r for r in rules if r["id"] == "workspace.tag-me")
        assert match["granted_by"] == "workspace"

    def test_explicit_default_decision_in_workspace_overrides_user(self, permission_env: dict) -> None:
        """A workspace layer that explicitly sets default_decision wins over user."""
        self._install_workspace_permissions(
            permission_env,
            {"policy": {"default_decision": "deny", "rules": []}},
        )

        outside = permission_env["tmp"] / "elsewhere.txt"
        result = GriptapeNodes.handle_request(
            WriteFileRequest(
                file_path=str(outside),
                content="hi",
                existing_file_policy=ExistingFilePolicy.OVERWRITE,
            )
        )
        # Workspace's explicit deny default fires; user layer's silent ALLOW
        # default is treated as unset and does not override.
        assert isinstance(result, WriteFileResultFailure)
        assert not outside.exists()

    def test_grant_only_persists_user_layer_rules(self, permission_env: dict) -> None:
        """Granting a rule writes to user config, not workspace/project layers."""
        self._install_workspace_permissions(
            permission_env,
            {
                "policy": {
                    "rules": [
                        {
                            "id": "workspace.read-only",
                            "decision": "deny",
                            "when": {"action": {"request_type": {"op": "glob", "pattern": "*"}}},
                        }
                    ]
                }
            },
        )

        # Granting a user rule should land only in the user config file; the
        # workspace rule must remain in memory because it lives outside the
        # persisted user file.
        _grant(
            {
                "id": "user.added",
                "decision": "allow",
                "when": {"action": {"request_type": {"op": "equals", "value": "ReadFileRequest"}}},
            }
        )
        on_disk = json.loads(permission_env["config_path"].read_text())
        rule_ids = [r["id"] for r in on_disk["permissions"]["policy"]["rules"]]
        assert rule_ids == ["user.added"]
        merged = GriptapeNodes.handle_request(GetEffectivePolicyRequest())
        assert isinstance(merged, GetEffectivePolicyResultSuccess)
        merged_ids = [r["id"] for r in merged.policy["rules"]]
        assert "workspace.read-only" in merged_ids
        assert "user.added" in merged_ids

    def test_revoke_refuses_non_user_layer_rule_id(self, permission_env: dict) -> None:
        """Revoke targets only the user layer; workspace-layer rule ids are read-only."""
        self._install_workspace_permissions(
            permission_env,
            {
                "policy": {
                    "rules": [
                        {
                            "id": "workspace.locked",
                            "decision": "deny",
                            "when": {"action": {"request_type": {"op": "glob", "pattern": "*"}}},
                        }
                    ]
                }
            },
        )

        result = GriptapeNodes.handle_request(RevokePermissionRuleRequest(rule_id="workspace.locked"))
        assert isinstance(result, RevokePermissionRuleResultFailure)
        # And the rule is still active.
        merged = GriptapeNodes.handle_request(GetEffectivePolicyRequest())
        assert isinstance(merged, GetEffectivePolicyResultSuccess)
        assert any(r["id"] == "workspace.locked" for r in merged.policy["rules"])
