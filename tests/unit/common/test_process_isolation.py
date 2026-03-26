"""Unit tests for process-isolated library execution components.

Tests for ProxyNode and event-based communication.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.proxy_node import ParameterSchema, ProxyNode
from griptape_nodes.retained_mode.events.execution_events import (
    ExecuteRemoteNodeRequest,
    ExecuteRemoteNodeResultSuccess,
)


class TestParameterSchema:
    """Tests for ParameterSchema serialization round-trips."""

    def test_roundtrip(self) -> None:
        schema = ParameterSchema(
            name="input_1",
            type="str",
            input_types=["str", "int"],
            output_type="str",
            allowed_modes=["INPUT", "PROPERTY"],
            default_value="default",
            tooltip="A tooltip",
        )
        data = schema.to_dict()
        restored = ParameterSchema.from_dict(data)

        assert restored.name == "input_1"
        assert restored.type == "str"
        assert restored.input_types == ["str", "int"]
        assert restored.output_type == "str"
        assert restored.allowed_modes == ["INPUT", "PROPERTY"]
        assert restored.default_value == "default"
        assert restored.tooltip == "A tooltip"


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
    """Tests for ProxyNode parameter construction and behavior."""

    def _make_proxy(self, schemas: list[ParameterSchema] | None = None) -> ProxyNode:
        if schemas is None:
            schemas = [
                ParameterSchema(
                    name="input_1",
                    type="str",
                    input_types=["str"],
                    output_type="str",
                    allowed_modes=["INPUT", "PROPERTY"],
                    default_value="",
                    tooltip="First input",
                ),
                ParameterSchema(
                    name="output",
                    type="str",
                    output_type="str",
                    allowed_modes=["OUTPUT"],
                    tooltip="Output value",
                ),
            ]
        return ProxyNode(
            name="test_proxy",
            library_name="test_lib",
            node_type="TestNode",
            parameter_schemas=schemas,
        )

    def test_parameters_created_from_schema(self) -> None:
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
        schemas = [
            ParameterSchema(
                name="exec_out",
                type="parametercontroltype",
                output_type="parametercontroltype",
                allowed_modes=["OUTPUT"],
            ),
        ]
        proxy = self._make_proxy(schemas=schemas)

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
