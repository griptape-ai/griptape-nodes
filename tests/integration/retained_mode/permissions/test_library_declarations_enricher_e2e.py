"""End-to-end test for the LibraryManager-published declarations fact.

`LibraryManager` registers a request enricher that parses the library JSON
referenced by a `RegisterLibraryFromFileRequest` and exposes its declarations
under `request.metadata.declarations.*`. This test verifies that policies can
match against authored library declarations without any test-side stub.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

import griptape_nodes.retained_mode.managers.config_manager as config_manager_module
from griptape_nodes.retained_mode.events.library_events import RegisterLibraryFromFileRequest
from griptape_nodes.retained_mode.events.permission_events import GrantPermissionRuleRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.settings import LIBRARIES_TO_REGISTER_KEY
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
            yield {"gn": gn, "tmp": tmp_path}
        SingletonMeta._instances.clear()


def _write_library_json(directory: Path, *, name: str, declarations: list[dict]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "griptape_nodes_library.json"
    json_path.write_text(
        json.dumps(
            {
                "name": name,
                "library_schema_version": "0.8.0",
                "metadata": {
                    "author": "test",
                    "description": "test",
                    "library_version": "0.0.1",
                    "engine_version": "0.85.0",
                    "tags": [],
                    "declarations": declarations,
                },
                "categories": [],
                "nodes": [],
            }
        )
    )
    return json_path


def _grant(rule: dict) -> None:
    GriptapeNodes.handle_request(GrantPermissionRuleRequest(rule=rule))


class TestLibraryDeclarationsEnricher:
    def test_labs_stage_blocks_registration(self, permission_env: dict) -> None:
        """A library declaring lifecycle_stage = LABS is blocked by a labs-deny rule."""
        json_path = _write_library_json(
            permission_env["tmp"] / "labs-lib",
            name="My Labs Library",
            declarations=[{"type": "lifecycle_stage", "stage": "LABS"}],
        )
        _grant(
            {
                "id": "user.deny-labs-libraries",
                "decision": "deny",
                "reason": "labs-stage libraries are not permitted",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "RegisterLibraryFromFileRequest"}},
                    "context": {
                        "facts": {
                            "request.metadata.declarations.lifecycle_stage": {
                                "op": "equals",
                                "value": "LABS",
                            }
                        }
                    },
                },
            }
        )
        result = GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path=str(json_path)))
        assert not result.succeeded()
        assert "user.deny-labs-libraries" in str(result.result_details)

    def test_stable_stage_passes_permission_gate(self, permission_env: dict) -> None:
        """A library declaring lifecycle_stage = STABLE is not blocked by the labs-deny rule."""
        json_path = _write_library_json(
            permission_env["tmp"] / "stable-lib",
            name="My Stable Library",
            declarations=[{"type": "lifecycle_stage", "stage": "STABLE"}],
        )
        _grant(
            {
                "id": "user.deny-labs-libraries",
                "decision": "deny",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "RegisterLibraryFromFileRequest"}},
                    "context": {
                        "facts": {
                            "request.metadata.declarations.lifecycle_stage": {
                                "op": "equals",
                                "value": "LABS",
                            }
                        }
                    },
                },
            }
        )
        # The library will fail to *load* (no real nodes in the fixture), but the
        # permission gate must let the request through. Audit-log inspection
        # tells us cleanly whether perms allowed or denied.
        GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path=str(json_path)))
        decisions = [
            d
            for d in permission_env["gn"].PermissionManager().list_recent_decisions()
            if d["action_request_type"] == "RegisterLibraryFromFileRequest"
        ]
        assert decisions, "expected at least one decision for the register request"
        assert decisions[-1]["rule_id"] != "user.deny-labs-libraries"

    def test_block_by_declaration_type_via_in_operator(self, permission_env: dict) -> None:
        """`in` matcher works against the flattened declaration-types list."""
        json_path = _write_library_json(
            permission_env["tmp"] / "labs-lib2",
            name="My Library",
            declarations=[{"type": "lifecycle_stage", "stage": "BETA"}],
        )
        _grant(
            {
                "id": "user.deny-libs-with-lifecycle-decl",
                "decision": "deny",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "RegisterLibraryFromFileRequest"}},
                    "context": {
                        "facts": {
                            "request.metadata.declarations.types": {
                                "op": "in",
                                "values": ["lifecycle_stage"],
                            }
                        }
                    },
                },
            }
        )
        result = GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path=str(json_path)))
        assert not result.succeeded()
        assert "user.deny-libs-with-lifecycle-decl" in str(result.result_details)

    def test_directory_path_resolves_to_library_json(self, permission_env: dict) -> None:
        """The enricher accepts a directory containing griptape_nodes_library.json."""
        lib_dir = permission_env["tmp"] / "dir-lib"
        _write_library_json(
            lib_dir,
            name="Dir Library",
            declarations=[{"type": "lifecycle_stage", "stage": "LABS"}],
        )
        _grant(
            {
                "id": "user.deny-labs-libraries",
                "decision": "deny",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "RegisterLibraryFromFileRequest"}},
                    "context": {
                        "facts": {
                            "request.metadata.declarations.lifecycle_stage": {
                                "op": "equals",
                                "value": "LABS",
                            }
                        }
                    },
                },
            }
        )
        # Pass the directory, not the JSON path. The enricher resolves it.
        result = GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path=str(lib_dir)))
        assert not result.succeeded()
        assert "user.deny-labs-libraries" in str(result.result_details)

    def test_library_name_registration_is_gated(self, permission_env: dict) -> None:
        """A by-name registration is gated by the same declaration rules as a by-path one."""
        json_path = _write_library_json(
            permission_env["tmp"] / "named-labs-lib",
            name="My Named Labs Library",
            declarations=[{"type": "lifecycle_stage", "stage": "LABS"}],
        )
        # Register by path first (no rule active yet) so the LibraryManager
        # tracks the library and can later resolve it by name.
        GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(file_path=str(json_path)))
        assert (
            permission_env["gn"].LibraryManager().get_library_info_by_library_name("My Named Labs Library") is not None
        ), "expected the by-path registration to track the library so it is addressable by name"
        _grant(
            {
                "id": "user.deny-labs-libraries",
                "decision": "deny",
                "reason": "labs-stage libraries are not permitted",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "RegisterLibraryFromFileRequest"}},
                    "context": {
                        "facts": {
                            "request.metadata.declarations.lifecycle_stage": {
                                "op": "equals",
                                "value": "LABS",
                            }
                        }
                    },
                },
            }
        )
        # The by-name path must resolve to the tracked JSON and be denied; if the
        # enricher returned no facts for the name, the deny would not fire.
        result = GriptapeNodes.handle_request(RegisterLibraryFromFileRequest(library_name="My Named Labs Library"))
        assert not result.succeeded()
        assert "user.deny-labs-libraries" in str(result.result_details)

    def test_discoverable_by_name_registration_is_gated(self, permission_env: dict) -> None:
        """An untracked-but-discoverable library registered by name is gated when discovery is allowed."""
        json_path = _write_library_json(
            permission_env["tmp"] / "discoverable-labs-lib",
            name="Discoverable Labs Library",
            declarations=[{"type": "lifecycle_stage", "stage": "LABS"}],
        )
        # Make the library discoverable via config without pre-tracking it,
        # mirroring a search path added after startup. The name is unknown to the
        # manager until the handler runs discovery, which happens after the gate.
        permission_env["gn"].ConfigManager().set_config_value(LIBRARIES_TO_REGISTER_KEY, [str(json_path)])
        assert (
            permission_env["gn"].LibraryManager().get_library_info_by_library_name("Discoverable Labs Library") is None
        ), "library must be untracked at gate-evaluation time for this test to be meaningful"
        _grant(
            {
                "id": "user.deny-labs-libraries",
                "decision": "deny",
                "reason": "labs-stage libraries are not permitted",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "RegisterLibraryFromFileRequest"}},
                    "context": {
                        "facts": {
                            "request.metadata.declarations.lifecycle_stage": {
                                "op": "equals",
                                "value": "LABS",
                            }
                        }
                    },
                },
            }
        )
        # The gate must resolve the untracked name via a read-only discovery scan
        # and deny before the handler ever discovers and loads the library.
        result = GriptapeNodes.handle_request(
            RegisterLibraryFromFileRequest(
                library_name="Discoverable Labs Library", perform_discovery_if_not_found=True
            )
        )
        assert not result.succeeded()
        assert "user.deny-labs-libraries" in str(result.result_details)

    def test_malformed_library_json_falls_through_cleanly(self, permission_env: dict) -> None:
        """A library file with broken JSON yields empty facts, not a crash."""
        broken = permission_env["tmp"] / "broken-lib"
        broken.mkdir()
        (broken / "griptape_nodes_library.json").write_text("{this is not valid json")
        _grant(
            {
                "id": "user.deny-labs-libraries",
                "decision": "deny",
                "when": {
                    "action": {"request_type": {"op": "equals", "value": "RegisterLibraryFromFileRequest"}},
                    "context": {
                        "facts": {
                            "request.metadata.declarations.lifecycle_stage": {
                                "op": "equals",
                                "value": "LABS",
                            }
                        }
                    },
                },
            }
        )
        # The labs-deny rule must NOT match because the enricher gracefully
        # returned no facts; permission evaluation falls through to the policy
        # default. The request will fail downstream during actual loading,
        # but not because of the labs rule.
        GriptapeNodes.handle_request(
            RegisterLibraryFromFileRequest(file_path=str(broken / "griptape_nodes_library.json"))
        )
        decisions = [
            d
            for d in permission_env["gn"].PermissionManager().list_recent_decisions()
            if d["action_request_type"] == "RegisterLibraryFromFileRequest"
        ]
        assert decisions, "expected at least one decision"
        assert decisions[-1]["rule_id"] != "user.deny-labs-libraries"
