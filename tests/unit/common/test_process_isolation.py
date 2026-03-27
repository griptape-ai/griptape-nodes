"""Unit tests for process-isolated library execution components.

Tests for ProxyNode and event-based communication.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.proxy_node import ProxyNode
from griptape_nodes.retained_mode.events.execution_events import (
    ExecuteRemoteNodeRequest,
    ExecuteRemoteNodeResultSuccess,
)


def _make_tree(children: list[dict] | None = None) -> dict:
    """Build a root_element_tree dict for testing."""
    if children is None:
        children = [
            {
                "element_type": "Parameter",
                "name": "input_1",
                "type": "str",
                "input_types": ["str"],
                "output_type": "str",
                "mode_allowed_input": True,
                "mode_allowed_property": True,
                "mode_allowed_output": False,
                "default_value": "",
                "tooltip": "First input",
            },
            {
                "element_type": "Parameter",
                "name": "output",
                "type": "str",
                "output_type": "str",
                "mode_allowed_input": False,
                "mode_allowed_property": False,
                "mode_allowed_output": True,
                "tooltip": "Output value",
            },
        ]
    return {"element_type": "BaseNodeElement", "children": children}


class TestExecuteRemoteNodeEvents:
    """Tests for ExecuteRemoteNodeRequest/Result event types."""

    def test_request_fields(self) -> None:
        request = ExecuteRemoteNodeRequest(
            node_name="merge1",
            parameter_values={"input_1": "hello", "input_2": "world"},
            entry_control_parameter_name="exec",
        )

        assert request.node_name == "merge1"
        assert request.parameter_values == {"input_1": "hello", "input_2": "world"}
        assert request.entry_control_parameter_name == "exec"

    def test_result_fields(self) -> None:
        result = ExecuteRemoteNodeResultSuccess(
            node_name="merge1",
            parameter_output_values={"output": "hello world"},
            next_control_output_name="exec_out",
            result_details="Success",
        )

        assert result.node_name == "merge1"
        assert result.parameter_output_values == {"output": "hello world"}
        assert result.next_control_output_name == "exec_out"


class TestProxyNode:
    """Tests for ProxyNode construction from element tree and behavior."""

    def _make_proxy(self, tree: dict | None = None) -> ProxyNode:
        if tree is None:
            tree = _make_tree()
        return ProxyNode(
            name="test_proxy",
            library_name="test_lib",
            node_type="TestNode",
            root_element_tree=tree,
        )

    def test_parameters_created_from_tree(self) -> None:
        proxy = self._make_proxy()

        param_names = [p.name for p in proxy.parameters]
        assert "input_1" in param_names
        assert "output" in param_names

    def test_parameter_modes(self) -> None:
        proxy = self._make_proxy()

        input_param = proxy.get_parameter_by_name("input_1")
        assert input_param is not None
        assert ParameterMode.INPUT in input_param.allowed_modes
        assert ParameterMode.PROPERTY in input_param.allowed_modes

        output_param = proxy.get_parameter_by_name("output")
        assert output_param is not None
        assert ParameterMode.OUTPUT in output_param.allowed_modes

    def test_library_name_and_node_type(self) -> None:
        proxy = self._make_proxy()

        assert proxy.library_name == "test_lib"
        assert proxy.node_type == "TestNode"

    def test_allows_all_connections(self) -> None:
        proxy = self._make_proxy()
        mock_node = MagicMock()
        mock_param = MagicMock()

        assert proxy.allow_incoming_connection(mock_node, mock_param, mock_param) is True
        assert proxy.allow_outgoing_connection(mock_param, mock_node, mock_param) is True

    def test_groups_preserve_order_and_nesting(self) -> None:
        tree = _make_tree(
            children=[
                {
                    "element_type": "Parameter",
                    "name": "model",
                    "type": "str",
                    "mode_allowed_input": False,
                    "mode_allowed_property": True,
                    "mode_allowed_output": False,
                },
                {
                    "element_type": "ParameterGroup",
                    "name": "Settings",
                    "ui_options": {"collapsed": True},
                    "children": [
                        {
                            "element_type": "Parameter",
                            "name": "seed",
                            "type": "int",
                            "mode_allowed_input": False,
                            "mode_allowed_property": True,
                            "mode_allowed_output": False,
                        },
                    ],
                },
                {
                    "element_type": "Parameter",
                    "name": "output",
                    "type": "str",
                    "mode_allowed_input": False,
                    "mode_allowed_property": False,
                    "mode_allowed_output": True,
                },
            ]
        )
        proxy = self._make_proxy(tree=tree)

        # All parameters should be found
        param_names = [p.name for p in proxy.parameters]
        assert param_names == ["model", "seed", "output"]

        # seed should be inside the Settings group
        seed_param = proxy.get_parameter_by_name("seed")
        assert seed_param is not None
        assert seed_param.parent_group_name == "Settings"

        # model and output should be at root level
        model_param = proxy.get_parameter_by_name("model")
        assert model_param is not None
        assert model_param.parent_group_name is None

        # The root children order should be: model, Settings group, output
        root_children = proxy.root_ui_element.children
        assert root_children[0].name == "model"
        assert root_children[1].name == "Settings"
        assert root_children[2].name == "output"

    @pytest.mark.asyncio
    async def test_aprocess_sends_execute_command(self) -> None:
        proxy = self._make_proxy()
        proxy.parameter_values["input_1"] = "hello"

        mock_result = ExecuteRemoteNodeResultSuccess(
            node_name="test_proxy",
            parameter_output_values={"output": "hello world"},
            next_control_output_name=None,
            result_details="Success",
        )

        mock_process_manager = AsyncMock()
        mock_process_manager.execute_node.return_value = mock_result

        with patch(
            "griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes.LibraryProcessManager",
            return_value=mock_process_manager,
        ):
            await proxy.aprocess()

        assert proxy.parameter_output_values["output"] == "hello world"
        mock_process_manager.execute_node.assert_called_once_with(
            library_name="test_lib",
            node_name="test_proxy",
            parameter_values={"input_1": "hello"},
            entry_control_parameter_name=None,
        )

    @pytest.mark.asyncio
    async def test_aprocess_sets_control_output(self) -> None:
        tree = _make_tree(
            children=[
                {
                    "element_type": "Parameter",
                    "name": "exec_out",
                    "type": "parametercontroltype",
                    "output_type": "parametercontroltype",
                    "mode_allowed_input": False,
                    "mode_allowed_property": False,
                    "mode_allowed_output": True,
                },
            ]
        )
        proxy = self._make_proxy(tree=tree)

        mock_result = ExecuteRemoteNodeResultSuccess(
            node_name="test_proxy",
            parameter_output_values={},
            next_control_output_name="exec_out",
            result_details="Success",
        )

        mock_process_manager = AsyncMock()
        mock_process_manager.execute_node.return_value = mock_result

        with patch(
            "griptape_nodes.retained_mode.griptape_nodes.GriptapeNodes.LibraryProcessManager",
            return_value=mock_process_manager,
        ):
            await proxy.aprocess()

        control_output = proxy.get_next_control_output()
        assert control_output is not None
        assert control_output.name == "exec_out"
