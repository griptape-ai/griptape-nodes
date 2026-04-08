from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.execution_events import (
    CreateWorkerNodeRequest,
    CreateWorkerNodeResultFailure,
    CreateWorkerNodeResultSuccess,
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

    @pytest.mark.asyncio
    async def test_execute_node_not_found(self) -> None:
        node_manager = self._get_node_manager()

        request = ExecuteNodeRequest(node_name="nonexistent_node")
        result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultFailure)
        assert "nonexistent_node" in str(result.result_details)

    @pytest.mark.asyncio
    async def test_execute_node_success(self) -> None:
        node_manager = self._get_node_manager()
        mock_node = self._make_mock_node()

        with patch.object(node_manager, "get_node_by_name", return_value=mock_node):
            request = ExecuteNodeRequest(
                node_name="test_node",
                parameter_values={"input_param": "input_value"},
            )
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultSuccess)
        assert result.parameter_output_values == {"output_param": "output_value"}
        mock_node.set_parameter_value.assert_called_once_with("input_param", "input_value")
        mock_node.aprocess.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_node_success_no_params(self) -> None:
        node_manager = self._get_node_manager()
        mock_node = self._make_mock_node()

        with patch.object(node_manager, "get_node_by_name", return_value=mock_node):
            request = ExecuteNodeRequest(node_name="test_node")
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultSuccess)
        mock_node.set_parameter_value.assert_not_called()
        mock_node.aprocess.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_node_set_parameter_fails(self) -> None:
        node_manager = self._get_node_manager()
        mock_node = self._make_mock_node()
        mock_node.set_parameter_value.side_effect = ValueError("bad value")

        with patch.object(node_manager, "get_node_by_name", return_value=mock_node):
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

        with patch.object(node_manager, "get_node_by_name", return_value=mock_node):
            request = ExecuteNodeRequest(node_name="test_node")
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultFailure)
        assert "process exploded" in str(result.result_details)

    @pytest.mark.asyncio
    async def test_execute_node_multiple_params(self) -> None:
        node_manager = self._get_node_manager()
        mock_node = self._make_mock_node()

        with patch.object(node_manager, "get_node_by_name", return_value=mock_node):
            request = ExecuteNodeRequest(
                node_name="test_node",
                parameter_values={"param_a": 1, "param_b": "two", "param_c": [3]},
            )
            result = await node_manager.on_execute_node_request(request)

        assert isinstance(result, ExecuteNodeResultSuccess)
        expected_param_count = 3
        assert mock_node.set_parameter_value.call_count == expected_param_count


class TestCreateWorkerNode:
    def _get_node_manager(self) -> NodeManager:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        return GriptapeNodes.NodeManager()

    def test_creates_and_registers_node(self) -> None:
        node_manager = self._get_node_manager()
        mock_node = MagicMock(spec=BaseNode)
        mock_node.name = "test_node"
        mock_obj_mgr = MagicMock()
        mock_obj_mgr.attempt_get_object_by_name_as_type.return_value = None

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
            request = CreateWorkerNodeRequest(
                node_name="test_node",
                node_type="SomeNodeType",
                library_name="some_library",
            )
            result = node_manager.on_create_worker_node_request(request)

        assert isinstance(result, CreateWorkerNodeResultSuccess)
        assert result.node_name == "test_node"
        mock_create.assert_called_once_with(
            node_type="SomeNodeType",
            name="test_node",
            metadata={},
            specific_library_name="some_library",
        )
        mock_obj_mgr.add_object_by_name.assert_called_once_with(mock_node.name, mock_node)

    def test_idempotent_when_node_exists(self) -> None:
        node_manager = self._get_node_manager()
        mock_obj_mgr = MagicMock()
        mock_obj_mgr.attempt_get_object_by_name_as_type.return_value = MagicMock(spec=BaseNode)

        with (
            patch(
                "griptape_nodes.retained_mode.managers.node_manager.GriptapeNodes.ObjectManager",
                return_value=mock_obj_mgr,
            ),
            patch(
                "griptape_nodes.retained_mode.managers.node_manager.LibraryRegistry.create_node",
            ) as mock_create,
        ):
            request = CreateWorkerNodeRequest(
                node_name="existing_node",
                node_type="SomeNodeType",
            )
            result = node_manager.on_create_worker_node_request(request)

        assert isinstance(result, CreateWorkerNodeResultSuccess)
        assert result.node_name == "existing_node"
        mock_create.assert_not_called()

    def test_fails_when_create_node_raises(self) -> None:
        node_manager = self._get_node_manager()
        mock_obj_mgr = MagicMock()
        mock_obj_mgr.attempt_get_object_by_name_as_type.return_value = None

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
            request = CreateWorkerNodeRequest(
                node_name="test_node",
                node_type="SomeNodeType",
            )
            result = node_manager.on_create_worker_node_request(request)

        assert isinstance(result, CreateWorkerNodeResultFailure)
        assert "test_node" in str(result.result_details)
        assert "SomeNodeType" in str(result.result_details)
        assert "library not loaded" in str(result.result_details)
