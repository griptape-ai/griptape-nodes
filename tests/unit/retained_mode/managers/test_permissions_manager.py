"""Tests for PermissionsManager."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from griptape_nodes.node_library.library_properties import (
    ExecuteArbitraryCodeNodeProperty,
    ModelCatalogLibraryProperty,
    ModelEntitlement,
    ModelUsageNodeProperty,
    PermissionCatalogLibraryProperty,
    PermissionDeclaration,
    RequiredPermissionsNodeProperty,
)
from griptape_nodes.node_library.library_registry import (
    CategoryDefinition,
    LibraryMetadata,
    LibraryRegistry,
    LibrarySchema,
    NodeDefinition,
    NodeMetadata,
)
from griptape_nodes.node_library.permission_builtins import (
    RUN_ARBITRARY_PYTHON,
)
from griptape_nodes.node_library.workflow_registry import LibraryNameAndNodeType
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry
from griptape_nodes.retained_mode.events.permission_events import (
    DenialReasonCode,
    EvaluatePermissionDenied,
    EvaluatePermissionGranted,
    EvaluatePermissionRequest,
    EvaluatePermissionResultFailure,
    EvaluationFailureCode,
    ListModelEntitlementsRequest,
    ListModelEntitlementsResultFailure,
    ListModelEntitlementsResultSuccess,
)
from griptape_nodes.retained_mode.managers.permissions_manager import PermissionsManager

if TYPE_CHECKING:
    from collections.abc import Iterator

# ---------- Fixtures / helpers ----------

TEST_LIBRARY_NAME = "TestPermissionsLibrary"


def _make_library_schema(
    *,
    name: str = TEST_LIBRARY_NAME,
    library_properties: list | None = None,
    nodes: list[NodeDefinition] | None = None,
) -> LibrarySchema:
    return LibrarySchema(
        name=name,
        library_schema_version=LibrarySchema.LATEST_SCHEMA_VERSION,
        metadata=LibraryMetadata(
            author="t",
            description="t",
            library_version="1.0.0",
            engine_version="1.0.0",
            tags=[],
            properties=library_properties or [],
        ),
        categories=[{"Test": CategoryDefinition(title="T", description="t", color="#000", icon="Folder")}],
        nodes=nodes or [],
    )


def _make_node_def(class_name: str, properties: list) -> NodeDefinition:
    return NodeDefinition(
        class_name=class_name,
        file_path=f"{class_name.lower()}.py",
        metadata=NodeMetadata(
            category="Test",
            description="t",
            display_name=class_name,
            properties=properties,
        ),
    )


@pytest.fixture
def registered_library() -> Iterator[str]:
    """Register a library with three node types exercising the three declaration paths."""
    schema = _make_library_schema(
        library_properties=[
            PermissionCatalogLibraryProperty(
                permissions={
                    "use_custom": PermissionDeclaration(description="custom"),
                    "use_openai": PermissionDeclaration(description="openai"),
                },
            ),
            ModelCatalogLibraryProperty(
                entitlements={
                    "openai_gpt4o": ModelEntitlement(
                        display_name="GPT-4o",
                        provider="OpenAI",
                        terms_url="https://example/terms",
                        requires_permission="use_openai",
                    ),
                }
            ),
        ],
        nodes=[
            # Declares via RequiredPermissionsNodeProperty.
            _make_node_def(
                "NodeWithDirectPermission",
                [RequiredPermissionsNodeProperty(names=["use_custom"])],
            ),
            # Declares via marker (inherits run_arbitrary_python via built-in mapping).
            _make_node_def(
                "NodeWithMarker",
                [ExecuteArbitraryCodeNodeProperty()],
            ),
            # Declares via model entitlement (inherits use_openai).
            _make_node_def(
                "NodeWithModelUsage",
                [ModelUsageNodeProperty(name="openai_gpt4o")],
            ),
            # Declares nothing.
            _make_node_def("NodeWithNoDeclarations", []),
        ],
    )
    LibraryRegistry.generate_new_library(library_data=schema)
    try:
        yield TEST_LIBRARY_NAME
    finally:
        LibraryRegistry.unregister_library(TEST_LIBRARY_NAME)


# ---------- is_allowed: unscoped escape hatch ----------


class TestIsAllowedUnscoped:
    def test_returns_true_for_any_name(self) -> None:
        manager = PermissionsManager()

        assert manager._is_allowed("anything") is True
        assert manager._is_allowed(RUN_ARBITRARY_PYTHON) is True


# ---------- check_permission: scoped evaluation ----------


@pytest.mark.usefixtures("registered_library")
class TestCheckPermissionGranted:
    """Each of the three declaration paths resolves to an `EvaluatePermissionGranted`."""

    def test_direct_required_permissions_grant(self) -> None:
        manager = PermissionsManager()

        result = manager._check_permission(
            subject=LibraryNameAndNodeType(library_name=TEST_LIBRARY_NAME, node_type="NodeWithDirectPermission"),
            permission_name="use_custom",
        )

        assert isinstance(result, EvaluatePermissionGranted)

    def test_marker_mapped_permission_grant(self) -> None:
        manager = PermissionsManager()

        result = manager._check_permission(
            subject=LibraryNameAndNodeType(library_name=TEST_LIBRARY_NAME, node_type="NodeWithMarker"),
            permission_name=RUN_ARBITRARY_PYTHON,
        )

        assert isinstance(result, EvaluatePermissionGranted)

    def test_model_entitlement_permission_grant(self) -> None:
        manager = PermissionsManager()

        result = manager._check_permission(
            subject=LibraryNameAndNodeType(library_name=TEST_LIBRARY_NAME, node_type="NodeWithModelUsage"),
            permission_name="use_openai",
        )

        assert isinstance(result, EvaluatePermissionGranted)


@pytest.mark.usefixtures("registered_library")
class TestCheckPermissionDenied:
    """Evaluation-level denials return `EvaluatePermissionDenied` with denial reasons."""

    def test_scope_violation_when_node_did_not_declare_permission(self) -> None:
        manager = PermissionsManager()

        result = manager._check_permission(
            subject=LibraryNameAndNodeType(library_name=TEST_LIBRARY_NAME, node_type="NodeWithNoDeclarations"),
            permission_name="use_custom",
        )

        assert isinstance(result, EvaluatePermissionDenied)
        assert len(result.denial_reasons) == 1
        assert result.denial_reasons[0].code is DenialReasonCode.DECLARATION_SCOPE_VIOLATION

    def test_unknown_permission_and_scope_violation_both_reported(self) -> None:
        """Checking an unknown permission on a node that doesn't declare it produces both reasons."""
        manager = PermissionsManager()

        result = manager._check_permission(
            subject=LibraryNameAndNodeType(library_name=TEST_LIBRARY_NAME, node_type="NodeWithNoDeclarations"),
            permission_name="nonexistent_permission",
        )

        assert isinstance(result, EvaluatePermissionDenied)
        codes = {reason.code for reason in result.denial_reasons}
        assert DenialReasonCode.UNKNOWN_PERMISSION in codes
        assert DenialReasonCode.DECLARATION_SCOPE_VIOLATION in codes

    def test_policy_denial_when_is_allowed_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Monkeypatch the evaluator to deny; verify POLICY_DENIED surfaces."""
        manager = PermissionsManager()
        monkeypatch.setattr(manager, "_is_allowed", lambda _name: False)

        result = manager._check_permission(
            subject=LibraryNameAndNodeType(library_name=TEST_LIBRARY_NAME, node_type="NodeWithDirectPermission"),
            permission_name="use_custom",
        )

        assert isinstance(result, EvaluatePermissionDenied)
        codes = [reason.code for reason in result.denial_reasons]
        assert codes == [DenialReasonCode.POLICY_DENIED]


@pytest.mark.usefixtures("registered_library")
class TestCheckPermissionEvaluationFailures:
    """Unresolvable subjects return `EvaluatePermissionResultFailure`, not denials."""

    def test_unknown_library_returns_failure(self) -> None:
        manager = PermissionsManager()

        result = manager._check_permission(
            subject=LibraryNameAndNodeType(library_name="NoSuchLibrary", node_type="X"),
            permission_name="anything",
        )

        assert isinstance(result, EvaluatePermissionResultFailure)
        assert result.failure_code is EvaluationFailureCode.UNKNOWN_LIBRARY

    def test_unknown_node_type_returns_failure(self) -> None:
        manager = PermissionsManager()

        result = manager._check_permission(
            subject=LibraryNameAndNodeType(library_name=TEST_LIBRARY_NAME, node_type="NoSuchNode"),
            permission_name="anything",
        )

        assert isinstance(result, EvaluatePermissionResultFailure)
        assert result.failure_code is EvaluationFailureCode.UNKNOWN_NODE_TYPE


# ---------- Event wiring ----------


class TestEventWiring:
    def test_handlers_registered_with_event_manager(self) -> None:
        event_manager = MagicMock()

        PermissionsManager(event_manager=event_manager)

        registered = {
            call.kwargs["request_type"] for call in event_manager.assign_manager_to_request_type.call_args_list
        }
        assert EvaluatePermissionRequest in registered
        assert ListModelEntitlementsRequest in registered

    def test_evaluate_handler_delegates_to_check_permission(self, registered_library: str) -> None:
        manager = PermissionsManager()
        request = EvaluatePermissionRequest(
            subject=LibraryNameAndNodeType(library_name=registered_library, node_type="NodeWithDirectPermission"),
            permission_name="use_custom",
        )

        result = manager.on_evaluate_permission_request(request)

        assert isinstance(result, EvaluatePermissionGranted)

    def test_list_handler_delegates_to_list_model_entitlements(self, registered_library: str) -> None:
        manager = PermissionsManager()
        request = ListModelEntitlementsRequest(
            subject=LibraryNameAndNodeType(library_name=registered_library, node_type="NodeWithModelUsage"),
        )

        result = manager.on_list_model_entitlements_request(request)

        assert isinstance(result, ListModelEntitlementsResultSuccess)
        assert [e.display_name for e in result.entitlements] == ["GPT-4o"]


class TestPermissionEventRegistration:
    def test_evaluate_request_registered(self) -> None:
        assert PayloadRegistry.get_type(EvaluatePermissionRequest.__name__) is EvaluatePermissionRequest

    def test_evaluate_granted_result_registered(self) -> None:
        assert PayloadRegistry.get_type(EvaluatePermissionGranted.__name__) is EvaluatePermissionGranted

    def test_evaluate_denied_result_registered(self) -> None:
        assert PayloadRegistry.get_type(EvaluatePermissionDenied.__name__) is EvaluatePermissionDenied

    def test_evaluate_failure_result_registered(self) -> None:
        assert PayloadRegistry.get_type(EvaluatePermissionResultFailure.__name__) is EvaluatePermissionResultFailure

    def test_list_request_registered(self) -> None:
        assert PayloadRegistry.get_type(ListModelEntitlementsRequest.__name__) is ListModelEntitlementsRequest

    def test_list_success_result_registered(self) -> None:
        assert (
            PayloadRegistry.get_type(ListModelEntitlementsResultSuccess.__name__) is ListModelEntitlementsResultSuccess
        )

    def test_list_failure_result_registered(self) -> None:
        assert (
            PayloadRegistry.get_type(ListModelEntitlementsResultFailure.__name__) is ListModelEntitlementsResultFailure
        )


# ---------- list_model_entitlements: filtered lookup ----------


@pytest.mark.usefixtures("registered_library")
class TestListModelEntitlements:
    """`list_model_entitlements` returns only the entitlements the caller is permitted to use."""

    def test_returns_entitlement_when_permission_is_granted(self) -> None:
        manager = PermissionsManager()

        result = manager._list_model_entitlements(
            subject=LibraryNameAndNodeType(library_name=TEST_LIBRARY_NAME, node_type="NodeWithModelUsage"),
        )

        assert isinstance(result, ListModelEntitlementsResultSuccess)
        assert [e.display_name for e in result.entitlements] == ["GPT-4o"]

    def test_filters_out_entitlement_when_permission_is_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An entitlement whose requires_permission is denied is excluded from the result."""
        manager = PermissionsManager()
        monkeypatch.setattr(manager, "_is_allowed", lambda name: name != "use_openai")

        result = manager._list_model_entitlements(
            subject=LibraryNameAndNodeType(library_name=TEST_LIBRARY_NAME, node_type="NodeWithModelUsage"),
        )

        assert isinstance(result, ListModelEntitlementsResultSuccess)
        assert result.entitlements == []

    def test_returns_empty_when_node_declares_no_model_usage(self) -> None:
        manager = PermissionsManager()

        result = manager._list_model_entitlements(
            subject=LibraryNameAndNodeType(library_name=TEST_LIBRARY_NAME, node_type="NodeWithNoDeclarations"),
        )

        assert isinstance(result, ListModelEntitlementsResultSuccess)
        assert result.entitlements == []

    def test_unknown_library_returns_failure(self) -> None:
        manager = PermissionsManager()

        result = manager._list_model_entitlements(
            subject=LibraryNameAndNodeType(library_name="NoSuchLibrary", node_type="X"),
        )

        assert isinstance(result, ListModelEntitlementsResultFailure)
        assert result.failure_code is EvaluationFailureCode.UNKNOWN_LIBRARY

    def test_unknown_node_type_returns_failure(self) -> None:
        manager = PermissionsManager()

        result = manager._list_model_entitlements(
            subject=LibraryNameAndNodeType(library_name=TEST_LIBRARY_NAME, node_type="NoSuchNode"),
        )

        assert isinstance(result, ListModelEntitlementsResultFailure)
        assert result.failure_code is EvaluationFailureCode.UNKNOWN_NODE_TYPE
