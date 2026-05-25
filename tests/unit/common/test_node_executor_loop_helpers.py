"""Contract tests for NodeExecutor loop-control helpers.

These tests cover small, near-pure helpers that decide loop control flow:

* ``get_node_parameter_mappings`` - select the start or end mapping out of a
  PackageNodesAsSerializedFlowResultSuccess.
* ``_should_break_loop`` - decide whether a packaged loop body's End node is
  signaling a break.
* ``_check_control_source_fired`` - decide whether a (source_node, source_param)
  pair has fired its control output.
* ``_find_source_for_control_param`` - return the first source for a given
  control parameter name, or None.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from griptape_nodes.common.node_executor import NodeExecutor
from griptape_nodes.exe_types.base_iterative_nodes import BaseIterativeEndNode

_GRIPTAPE_NODES_PATH = "griptape_nodes.common.node_executor.GriptapeNodes"


def _make_executor() -> NodeExecutor:
    return NodeExecutor.__new__(NodeExecutor)


def _make_package_result(
    *,
    start_node_name: str = "StartPkg",
    end_node_name: str = "EndPkg",
    start_param_mappings: dict[str, Any] | None = None,
    end_param_mappings: dict[str, Any] | None = None,
) -> MagicMock:
    """Mock PackageNodesAsSerializedFlowResultSuccess with start/end mappings at indices 0/1."""
    package_result = MagicMock()
    start_mapping = MagicMock()
    start_mapping.node_name = start_node_name
    start_mapping.parameter_mappings = start_param_mappings or {}
    end_mapping = MagicMock()
    end_mapping.node_name = end_node_name
    end_mapping.parameter_mappings = end_param_mappings or {}
    package_result.parameter_name_mappings = [start_mapping, end_mapping]
    return package_result


class TestGetNodeParameterMappings:
    """Returns index 0 for 'start', index 1 for 'end'; raises for anything else."""

    def test_returns_start_mapping_for_start(self) -> None:
        package = _make_package_result(start_node_name="MyStart")
        mapping = _make_executor().get_node_parameter_mappings(package, "start")
        assert mapping.node_name == "MyStart"

    def test_returns_end_mapping_for_end(self) -> None:
        package = _make_package_result(end_node_name="MyEnd")
        mapping = _make_executor().get_node_parameter_mappings(package, "end")
        assert mapping.node_name == "MyEnd"

    def test_is_case_insensitive(self) -> None:
        package = _make_package_result(start_node_name="MyStart", end_node_name="MyEnd")
        executor = _make_executor()
        assert executor.get_node_parameter_mappings(package, "START").node_name == "MyStart"
        assert executor.get_node_parameter_mappings(package, "End").node_name == "MyEnd"

    def test_raises_value_error_for_other_strings(self) -> None:
        package = _make_package_result()
        with pytest.raises(ValueError, match="middle"):
            _make_executor().get_node_parameter_mappings(package, "middle")


class TestShouldBreakLoop:
    """_should_break_loop returns True iff the deserialized End node signals a break."""

    @staticmethod
    def _make_end_node(
        *,
        is_iterative_end: bool = True,
        next_control_output: Any = None,
        break_signal: Any = None,
    ) -> Any:
        if not is_iterative_end:
            node = MagicMock()
            return node
        node = MagicMock(spec=BaseIterativeEndNode)
        node.get_next_control_output.return_value = next_control_output
        node.break_loop_signal_output = break_signal
        return node

    def test_returns_false_when_end_name_missing_from_mappings(self) -> None:
        package = _make_package_result(end_node_name="EndPkg")
        with patch(_GRIPTAPE_NODES_PATH):
            result = _make_executor()._should_break_loop({}, package)
        assert result is False

    def test_returns_false_when_deserialized_end_node_not_found(self) -> None:
        package = _make_package_result(end_node_name="EndPkg")
        mappings = {"EndPkg": "EndPkg_inst1"}

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.NodeManager.return_value.get_node_by_name.return_value = None
            result = _make_executor()._should_break_loop(mappings, package)

        assert result is False

    def test_returns_false_when_deserialized_node_is_not_iterative_end(self) -> None:
        package = _make_package_result(end_node_name="EndPkg")
        mappings = {"EndPkg": "EndPkg_inst1"}
        non_iterative_node = MagicMock()  # Not a BaseIterativeEndNode

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.NodeManager.return_value.get_node_by_name.return_value = non_iterative_node
            result = _make_executor()._should_break_loop(mappings, package)

        assert result is False

    def test_returns_false_when_no_next_control_output(self) -> None:
        package = _make_package_result(end_node_name="EndPkg")
        mappings = {"EndPkg": "EndPkg_inst1"}
        end_node = self._make_end_node(next_control_output=None)

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.NodeManager.return_value.get_node_by_name.return_value = end_node
            result = _make_executor()._should_break_loop(mappings, package)

        assert result is False

    def test_returns_false_when_next_control_output_is_not_break_signal(self) -> None:
        package = _make_package_result(end_node_name="EndPkg")
        mappings = {"EndPkg": "EndPkg_inst1"}
        not_break = object()
        break_signal = object()
        end_node = self._make_end_node(next_control_output=not_break, break_signal=break_signal)

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.NodeManager.return_value.get_node_by_name.return_value = end_node
            result = _make_executor()._should_break_loop(mappings, package)

        assert result is False

    def test_returns_true_when_next_control_output_matches_break_signal(self) -> None:
        package = _make_package_result(end_node_name="EndPkg")
        mappings = {"EndPkg": "EndPkg_inst1"}
        break_signal = object()
        end_node = self._make_end_node(next_control_output=break_signal, break_signal=break_signal)

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.NodeManager.return_value.get_node_by_name.return_value = end_node
            result = _make_executor()._should_break_loop(mappings, package)

        assert result is True


class TestCheckControlSourceFired:
    """_check_control_source_fired matches a node's next control output to a parameter."""

    @staticmethod
    def _make_source_node(*, next_control_output: Any, params: dict[str, Any] | None = None) -> Any:
        node = MagicMock()
        node.get_next_control_output.return_value = next_control_output
        params = params or {}
        node.get_parameter_by_name.side_effect = params.get
        return node

    def test_returns_false_when_source_is_none(self) -> None:
        with patch(_GRIPTAPE_NODES_PATH):
            assert _make_executor()._check_control_source_fired(None, {}) is False

    def test_returns_false_when_source_node_not_in_mappings(self) -> None:
        with patch(_GRIPTAPE_NODES_PATH):
            result = _make_executor()._check_control_source_fired(("SrcOrig", "out"), {})
        assert result is False

    def test_returns_false_when_node_manager_raises_value_error(self) -> None:
        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.NodeManager.return_value.get_node_by_name.side_effect = ValueError("not found")
            result = _make_executor()._check_control_source_fired(
                ("SrcOrig", "out"),
                {"SrcOrig": "Src_inst1"},
            )
        assert result is False

    def test_returns_false_when_node_manager_returns_none(self) -> None:
        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.NodeManager.return_value.get_node_by_name.return_value = None
            result = _make_executor()._check_control_source_fired(
                ("SrcOrig", "out"),
                {"SrcOrig": "Src_inst1"},
            )
        assert result is False

    def test_returns_false_when_no_next_control_output(self) -> None:
        node = self._make_source_node(next_control_output=None)
        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.NodeManager.return_value.get_node_by_name.return_value = node
            result = _make_executor()._check_control_source_fired(
                ("SrcOrig", "out"),
                {"SrcOrig": "Src_inst1"},
            )
        assert result is False

    def test_returns_true_when_next_control_output_matches_parameter(self) -> None:
        target_param = MagicMock()
        target_param.name = "out"
        node = self._make_source_node(
            next_control_output=target_param,
            params={"out": target_param},
        )
        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.NodeManager.return_value.get_node_by_name.return_value = node
            result = _make_executor()._check_control_source_fired(
                ("SrcOrig", "out"),
                {"SrcOrig": "Src_inst1"},
            )
        assert result is True

    def test_returns_false_when_next_control_output_is_a_different_parameter(self) -> None:
        wrong_param = MagicMock(name="wrong")
        target_param = MagicMock(name="target")
        node = self._make_source_node(
            next_control_output=wrong_param,
            params={"out": target_param},
        )
        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.NodeManager.return_value.get_node_by_name.return_value = node
            result = _make_executor()._check_control_source_fired(
                ("SrcOrig", "out"),
                {"SrcOrig": "Src_inst1"},
            )
        assert result is False


class TestFindSourceForControlParam:
    """_find_source_for_control_param returns the first source from the multi-source helper."""

    def test_returns_first_source_when_multiple_present(self) -> None:
        executor = _make_executor()
        with patch.object(
            NodeExecutor,
            "_find_sources_for_control_param",
            return_value=[("A", "out"), ("B", "out")],
        ) as mock_multi:
            result = executor._find_source_for_control_param([], "break_loop")

        assert result == ("A", "out")
        mock_multi.assert_called_once_with([], "break_loop")

    def test_returns_none_when_no_sources(self) -> None:
        executor = _make_executor()
        with patch.object(NodeExecutor, "_find_sources_for_control_param", return_value=[]):
            result = executor._find_source_for_control_param([], "break_loop")

        assert result is None
