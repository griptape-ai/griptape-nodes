from collections.abc import Iterator
from unittest.mock import Mock

import pytest

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.node_library.library_registry import (
    CategoryDefinition,
    LibraryMetadata,
    LibraryRegistry,
    LibrarySchema,
    NodeDefinition,
    NodeMetadata,
)

from .mocks import MockNode


class TestNodeTypes:
    """Test suite for node types functionality."""

    @pytest.mark.asyncio
    async def test_aprocess_with_multiple_yields(self) -> None:
        """Test that aprocess correctly handles nodes with multiple yields."""
        results = []

        def callable1() -> str:
            return "result1"

        def callable2() -> str:
            return "result2"

        def generator() -> AsyncResult:
            result1 = yield callable1
            results.append(result1)

            result2 = yield callable2
            results.append(result2)

        node = MockNode(process_result=generator())

        # Should complete without error
        await node.aprocess()

        # Verify all yields were processed
        assert results == ["result1", "result2"]


class TestConnectionRemovedHooks:
    def _make_param(self, name: str) -> Parameter:
        return Parameter(name=name, input_types=["str"], type="str", output_type="str", tooltip="test")

    def test_after_incoming_connection_removed_calls_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        callback = Mock()
        target_param.on_incoming_connection_removed.append(callback)

        target_node.after_incoming_connection_removed(source_node, source_param, target_param)

        callback.assert_called_once_with(target_param, "source_node", "source_param")

    def test_after_incoming_connection_removed_calls_multiple_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        callback1 = Mock()
        callback2 = Mock()
        target_param.on_incoming_connection_removed.append(callback1)
        target_param.on_incoming_connection_removed.append(callback2)

        target_node.after_incoming_connection_removed(source_node, source_param, target_param)

        callback1.assert_called_once_with(target_param, "source_node", "source_param")
        callback2.assert_called_once_with(target_param, "source_node", "source_param")

    def test_after_incoming_connection_removed_no_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        # Should not raise when no callbacks are registered
        target_node.after_incoming_connection_removed(source_node, source_param, target_param)

    def test_after_outgoing_connection_removed_calls_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        callback = Mock()
        source_param.on_outgoing_connection_removed.append(callback)

        source_node.after_outgoing_connection_removed(source_param, target_node, target_param)

        callback.assert_called_once_with(source_param, "target_node", "target_param")

    def test_after_outgoing_connection_removed_calls_multiple_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        callback1 = Mock()
        callback2 = Mock()
        source_param.on_outgoing_connection_removed.append(callback1)
        source_param.on_outgoing_connection_removed.append(callback2)

        source_node.after_outgoing_connection_removed(source_param, target_node, target_param)

        callback1.assert_called_once_with(source_param, "target_node", "target_param")
        callback2.assert_called_once_with(source_param, "target_node", "target_param")

    def test_after_outgoing_connection_removed_no_callbacks(self) -> None:
        source_node = MockNode(name="source_node")
        target_node = MockNode(name="target_node")
        source_param = self._make_param("source_param")
        target_param = self._make_param("target_param")

        # Should not raise when no callbacks are registered
        source_node.after_outgoing_connection_removed(source_param, target_node, target_param)


@pytest.fixture
def registered_check_permission_library() -> Iterator[str]:
    """Register a library used by TestBaseNodeCheckPermission.

    Declares a permission catalog with `use_custom`, and a node type `PermissionedNode`
    that references it via RequiredPermissionsNodeProperty.
    """
    from griptape_nodes.node_library.library_properties import (
        PermissionCatalogLibraryProperty,
        PermissionDeclaration,
        RequiredPermissionsNodeProperty,
    )

    library_name = "TestBaseNodeCheckPermissionLibrary"
    schema = LibrarySchema(
        name=library_name,
        library_schema_version=LibrarySchema.LATEST_SCHEMA_VERSION,
        metadata=LibraryMetadata(
            author="t",
            description="t",
            library_version="1.0.0",
            engine_version="1.0.0",
            tags=[],
            properties=[
                PermissionCatalogLibraryProperty(
                    permissions={"use_custom": PermissionDeclaration(description="custom")},
                ),
            ],
        ),
        categories=[{"Test": CategoryDefinition(title="Test", description="t", color="#000", icon="Folder")}],
        nodes=[
            NodeDefinition(
                class_name="PermissionedNode",
                file_path="permissioned.py",
                metadata=NodeMetadata(
                    category="Test",
                    description="t",
                    display_name="PermissionedNode",
                    properties=[RequiredPermissionsNodeProperty(names=["use_custom"])],
                ),
            ),
        ],
    )
    LibraryRegistry.generate_new_library(library_data=schema)
    try:
        yield library_name
    finally:
        LibraryRegistry.unregister_library(library_name)


class TestBaseNodeCheckPermission:
    """BaseNode.check_permission dispatches EvaluatePermissionRequest via handle_request."""

    def test_granted_permission_returns_granted_result(self, registered_check_permission_library: str) -> None:
        from griptape_nodes.retained_mode.events.permission_events import EvaluatePermissionGranted
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        GriptapeNodes()  # Ensure singleton init so GriptapeNodes.handle_request() works.
        node = MockNode(
            name="n",
            metadata={
                "library": registered_check_permission_library,
                "node_type": "PermissionedNode",
                "library_node_metadata": NodeMetadata(
                    category="Test",
                    description="t",
                    display_name="PermissionedNode",
                ),
            },
        )

        result = node.check_permission("use_custom")

        assert isinstance(result, EvaluatePermissionGranted)

    def test_scope_violation_returns_denied_with_reason(self, registered_check_permission_library: str) -> None:
        from griptape_nodes.retained_mode.events.permission_events import (
            DenialReasonCode,
            EvaluatePermissionDenied,
        )
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        GriptapeNodes()
        node = MockNode(
            name="n",
            metadata={
                "library": registered_check_permission_library,
                "node_type": "PermissionedNode",
                "library_node_metadata": NodeMetadata(
                    category="Test",
                    description="t",
                    display_name="PermissionedNode",
                ),
            },
        )

        result = node.check_permission("not_declared_by_this_node")

        assert isinstance(result, EvaluatePermissionDenied)
        codes = {reason.code for reason in result.denial_reasons}
        assert DenialReasonCode.DECLARATION_SCOPE_VIOLATION in codes


# Model-entitlement resolution now lives on PermissionsManager; see
# tests/unit/retained_mode/managers/test_permissions_manager.py::TestListModelEntitlements
# for the equivalent coverage.
