from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.execution_events import (
    ExecuteNodeRequest,
    ExecuteNodeResultFailure,
    ExecuteNodeResultSuccess,
)
from griptape_nodes.retained_mode.managers.node_manager import NodeManager


class TestExecuteNode:
    def _get_node_manager(self) -> NodeManager:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        return GriptapeNodes.NodeManager()

    def _make_mock_node(self, name: str = "test_node") -> MagicMock:
        node = MagicMock(spec=BaseNode)
        node.name = name
        node.aprocess = AsyncMock()
        node.parameter_output_values = {"output_param": "output_value"}
        return node

    def _make_mock_obj_mgr(self, existing_node: MagicMock | None = None) -> MagicMock:
        mock_obj_mgr = MagicMock()
        mock_obj_mgr.attempt_get_object_by_name_as_type.return_value = existing_node
        return mock_obj_mgr

    @pytest.mark.asyncio
    async def test_execute_node_not_found_no_metadata(self) -> None:
        """Node absent and no node_metadata provided → failure."""
        node_manager = self._get_node_manager()
        mock_obj_mgr = self._make_mock_obj_mgr(existing_node=None)

        with patch(
            "griptape_nodes.retained_mode.managers.node_manager.GriptapeNodes.ObjectManager",
            return_value=mock_obj_mgr,
        ):
            request = ExecuteNodeRequest(node_name="nonexistent_node")
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultFailure)
        assert "nonexistent_node" in str(result.result_details)

    @pytest.mark.asyncio
    async def test_execute_node_not_found_metadata_missing_node_type(self) -> None:
        """Node absent, node_metadata present but missing 'node_type' → failure."""
        node_manager = self._get_node_manager()
        mock_obj_mgr = self._make_mock_obj_mgr(existing_node=None)

        with patch(
            "griptape_nodes.retained_mode.managers.node_manager.GriptapeNodes.ObjectManager",
            return_value=mock_obj_mgr,
        ):
            request = ExecuteNodeRequest(
                node_name="some_node",
                node_metadata={"library": "some_library"},
            )
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultFailure)
        assert "node_type" in str(result.result_details)

    @pytest.mark.asyncio
    async def test_execute_node_creates_and_runs_when_absent(self) -> None:
        """Node absent, valid node_metadata → node created then executed."""
        node_manager = self._get_node_manager()
        mock_node = self._make_mock_node()
        mock_obj_mgr = self._make_mock_obj_mgr(existing_node=None)

        with (
            patch(
                "griptape_nodes.retained_mode.managers.node_manager.GriptapeNodes.ObjectManager",
                return_value=mock_obj_mgr,
            ),
            patch(
                "griptape_nodes.retained_mode.managers.node_manager.LibraryRegistry.create_node",
                return_value=mock_node,
            ) as mock_create,
        ):
            request = ExecuteNodeRequest(
                node_name="test_node",
                parameter_values={"input_param": "value"},
                node_metadata={"node_type": "SomeNodeType", "library": "some_library"},
            )
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultSuccess)
        mock_create.assert_called_once_with(
            node_type="SomeNodeType",
            name="test_node",
            metadata={"node_type": "SomeNodeType", "library": "some_library"},
            specific_library_name="some_library",
        )
        mock_obj_mgr.add_object_by_name.assert_called_once_with(mock_node.name, mock_node)
        mock_node.set_parameter_value.assert_called_once_with("input_param", "value")
        mock_node.aprocess.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_node_creation_failure(self) -> None:
        """Node absent, create_node raises → ExecuteNodeResultFailure."""
        node_manager = self._get_node_manager()
        mock_obj_mgr = self._make_mock_obj_mgr(existing_node=None)

        with (
            patch(
                "griptape_nodes.retained_mode.managers.node_manager.GriptapeNodes.ObjectManager",
                return_value=mock_obj_mgr,
            ),
            patch(
                "griptape_nodes.retained_mode.managers.node_manager.LibraryRegistry.create_node",
                side_effect=RuntimeError("library not loaded"),
            ),
        ):
            request = ExecuteNodeRequest(
                node_name="test_node",
                node_metadata={"node_type": "SomeNodeType", "library": "some_library"},
            )
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultFailure)
        assert "test_node" in str(result.result_details)
        assert "SomeNodeType" in str(result.result_details)
        assert "library not loaded" in str(result.result_details)

    @pytest.mark.asyncio
    async def test_execute_node_reuses_existing(self) -> None:
        """Node already exists → skips creation, executes directly."""
        node_manager = self._get_node_manager()
        mock_node = self._make_mock_node()
        mock_obj_mgr = self._make_mock_obj_mgr(existing_node=mock_node)

        with (
            patch(
                "griptape_nodes.retained_mode.managers.node_manager.GriptapeNodes.ObjectManager",
                return_value=mock_obj_mgr,
            ),
            patch(
                "griptape_nodes.retained_mode.managers.node_manager.LibraryRegistry.create_node",
            ) as mock_create,
        ):
            request = ExecuteNodeRequest(
                node_name="test_node",
                parameter_values={"input_param": "input_value"},
                node_metadata={"node_type": "SomeNodeType", "library": "some_library"},
            )
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultSuccess)
        mock_create.assert_not_called()
        mock_obj_mgr.add_object_by_name.assert_not_called()
        mock_node.set_parameter_value.assert_called_once_with("input_param", "input_value")
        mock_node.aprocess.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_node_success_no_params(self) -> None:
        node_manager = self._get_node_manager()
        mock_node = self._make_mock_node()
        mock_obj_mgr = self._make_mock_obj_mgr(existing_node=mock_node)

        with patch(
            "griptape_nodes.retained_mode.managers.node_manager.GriptapeNodes.ObjectManager",
            return_value=mock_obj_mgr,
        ):
            request = ExecuteNodeRequest(node_name="test_node", node_metadata={"node_type": "T"})
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultSuccess)
        mock_node.set_parameter_value.assert_not_called()
        mock_node.aprocess.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_node_set_parameter_fails(self) -> None:
        node_manager = self._get_node_manager()
        mock_node = self._make_mock_node()
        mock_node.set_parameter_value.side_effect = ValueError("bad value")
        mock_obj_mgr = self._make_mock_obj_mgr(existing_node=mock_node)

        with patch(
            "griptape_nodes.retained_mode.managers.node_manager.GriptapeNodes.ObjectManager",
            return_value=mock_obj_mgr,
        ):
            request = ExecuteNodeRequest(
                node_name="test_node",
                parameter_values={"bad_param": "bad_value"},
            )
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultFailure)
        assert "bad_param" in str(result.result_details)
        mock_node.aprocess.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execute_node_aprocess_fails(self) -> None:
        node_manager = self._get_node_manager()
        mock_node = self._make_mock_node()
        mock_node.aprocess.side_effect = RuntimeError("process exploded")
        mock_obj_mgr = self._make_mock_obj_mgr(existing_node=mock_node)

        with patch(
            "griptape_nodes.retained_mode.managers.node_manager.GriptapeNodes.ObjectManager",
            return_value=mock_obj_mgr,
        ):
            request = ExecuteNodeRequest(node_name="test_node")
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultFailure)
        assert "process exploded" in str(result.result_details)

    @pytest.mark.asyncio
    async def test_execute_node_multiple_params(self) -> None:
        node_manager = self._get_node_manager()
        mock_node = self._make_mock_node()
        mock_obj_mgr = self._make_mock_obj_mgr(existing_node=mock_node)

        with patch(
            "griptape_nodes.retained_mode.managers.node_manager.GriptapeNodes.ObjectManager",
            return_value=mock_obj_mgr,
        ):
            request = ExecuteNodeRequest(
                node_name="test_node",
                parameter_values={"param_a": 1, "param_b": "two", "param_c": [3]},
            )
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultSuccess)
        expected_param_count = 3
        assert mock_node.set_parameter_value.call_count == expected_param_count
