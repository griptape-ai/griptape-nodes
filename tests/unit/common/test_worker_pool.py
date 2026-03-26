"""Unit tests for process-isolated library execution components.

Tests for ProxyNode, IPC protocol, and LibraryProcessManager.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.exe_types.core_types import ParameterMode
from griptape_nodes.exe_types.proxy_node import ProxyNode
from griptape_nodes.ipc.protocol import (
    CREATE_NODE,
    CreateNodeCommand,
    CreateNodeResult,
    ExecuteNodeCommand,
    ExecuteNodeResult,
    IPCMessage,
    ParameterSchema,
)


class TestIPCProtocol:
    """Tests for IPC message serialization round-trips."""

    def test_ipc_message_roundtrip(self) -> None:
        msg = IPCMessage(message_id="abc123", message_type=CREATE_NODE, payload={"node_type": "Foo"})
        data = msg.to_dict()
        restored = IPCMessage.from_dict(data)

        assert restored.message_id == "abc123"
        assert restored.message_type == CREATE_NODE
        assert restored.payload == {"node_type": "Foo"}

    def test_create_node_command_roundtrip(self) -> None:
        cmd = CreateNodeCommand(node_type="MergeTexts", node_name="merge1", metadata={"library": "standard"})
        payload = cmd.to_payload()
        restored = CreateNodeCommand.from_payload(payload)

        assert restored.node_type == "MergeTexts"
        assert restored.node_name == "merge1"
        assert restored.metadata == {"library": "standard"}

    def test_execute_node_command_roundtrip(self) -> None:
        cmd = ExecuteNodeCommand(
            node_name="merge1",
            parameter_values={"input_1": "hello", "input_2": "world"},
            entry_control_parameter_name="exec",
        )
        payload = cmd.to_payload()
        restored = ExecuteNodeCommand.from_payload(payload)

        assert restored.node_name == "merge1"
        assert restored.parameter_values == {"input_1": "hello", "input_2": "world"}
        assert restored.entry_control_parameter_name == "exec"

    def test_create_node_result_roundtrip(self) -> None:
        result = CreateNodeResult(
            node_name="merge1",
            parameter_schemas=[
                ParameterSchema(name="input_1", type="str", input_types=["str"], output_type="str"),
                ParameterSchema(name="output", type="str", output_type="str", allowed_modes=["OUTPUT"]),
            ],
        )
        payload = result.to_payload()
        restored = CreateNodeResult.from_payload(payload)

        assert restored.node_name == "merge1"
        expected_schema_count = 2
        assert len(restored.parameter_schemas) == expected_schema_count
        assert restored.parameter_schemas[0].name == "input_1"
        assert restored.parameter_schemas[1].allowed_modes == ["OUTPUT"]

    def test_execute_node_result_roundtrip(self) -> None:
        result = ExecuteNodeResult(
            node_name="merge1",
            parameter_output_values={"output": "hello world"},
            next_control_output_name="exec_out",
        )
        payload = result.to_payload()
        restored = ExecuteNodeResult.from_payload(payload)

        assert restored.node_name == "merge1"
        assert restored.parameter_output_values == {"output": "hello world"}
        assert restored.next_control_output_name == "exec_out"

    def test_parameter_schema_roundtrip(self) -> None:
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

        mock_result = ExecuteNodeResult(
            node_name="test_proxy",
            parameter_output_values={"output": "hello world"},
            next_control_output_name=None,
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

        mock_result = ExecuteNodeResult(
            node_name="test_proxy",
            parameter_output_values={},
            next_control_output_name="exec_out",
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
