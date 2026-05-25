"""Contract tests for NodeExecutor helpers and SubflowNodeGroup execute() branches.

These tests describe the observable contract of:

* ``NodeExecutor.get_workflow_handler`` - returns the registered handler for a
  library, or raises ``ValueError`` with the library name in the message.
* ``NodeExecutor._deserialize_parameter_value`` - resolves UUID-referenced
  pickled bytes back into Python objects, with explicit fallbacks when the
  stored value is not a UUID reference, not a string, or not unpicklable.
* ``NodeExecutor._extract_parameter_output_values`` - merges per-node output
  dicts from a subprocess result, using the deserializer for UUID references
  and falling back to a pre-mapping flat shape for backward compatibility.
* ``NodeExecutor.execute`` - the remaining ``SubflowNodeGroup`` branches
  (private execution, library-name execution) and the unexpected-result-type
  edge case.
"""

import pickle
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from griptape_nodes.common.node_executor import NodeExecutor
from griptape_nodes.exe_types.node_groups import SubflowNodeGroup
from griptape_nodes.exe_types.node_types import LOCAL_EXECUTION, PRIVATE_EXECUTION
from griptape_nodes.retained_mode.events.execution_events import ExecuteNodeResultSuccess
from griptape_nodes.retained_mode.events.workflow_events import PublishWorkflowRequest

_GRIPTAPE_NODES_PATH = "griptape_nodes.common.node_executor.GriptapeNodes"


def _make_executor() -> NodeExecutor:
    return NodeExecutor.__new__(NodeExecutor)


def _make_subflow_node(execution_type: str) -> MagicMock:
    node = MagicMock(spec=SubflowNodeGroup)
    node.name = "Subflow"
    node.execution_environment = MagicMock()
    node.execution_environment.name = "execution_environment"
    node.get_parameter_value = MagicMock(return_value=execution_type)
    node.aprocess = AsyncMock()
    node.subflow_execution_component = MagicMock()
    node.subflow_execution_component.clear_execution_state = MagicMock()
    return node


class TestGetWorkflowHandler:
    """get_workflow_handler returns the PublishWorkflowRequest handler for a library."""

    def test_returns_registered_handler_for_known_library(self) -> None:
        sentinel_handler = object()
        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_lm = MagicMock()
            mock_lm.get_registered_event_handlers.return_value = {"my_lib": sentinel_handler}
            mock_gn.LibraryManager.return_value = mock_lm

            handler = _make_executor().get_workflow_handler("my_lib")

        assert handler is sentinel_handler
        mock_lm.get_registered_event_handlers.assert_called_once_with(PublishWorkflowRequest)

    def test_raises_value_error_when_library_unregistered(self) -> None:
        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_lm = MagicMock()
            mock_lm.get_registered_event_handlers.return_value = {}
            mock_gn.LibraryManager.return_value = mock_lm

            with pytest.raises(ValueError, match="missing_lib"):
                _make_executor().get_workflow_handler("missing_lib")


class TestDeserializeParameterValue:
    """_deserialize_parameter_value resolves UUID-referenced pickled values."""

    def test_returns_param_value_unchanged_when_not_a_uuid_reference(self) -> None:
        executor = _make_executor()
        sentinel = object()

        result = executor._deserialize_parameter_value(
            param_name="x",
            param_value=sentinel,
            unique_uuid_to_values={"some-uuid": "irrelevant"},
        )

        assert result is sentinel

    def test_returns_stored_value_directly_when_not_a_string(self) -> None:
        executor = _make_executor()
        stored = {"already": "deserialized"}

        result = executor._deserialize_parameter_value(
            param_name="x",
            param_value="uuid-1",
            unique_uuid_to_values={"uuid-1": stored},
        )

        assert result is stored

    def test_unpickles_string_representation_of_bytes(self) -> None:
        executor = _make_executor()
        original = {"answer": 42, "items": [1, 2, 3]}
        pickled_repr = repr(pickle.dumps(original))  # e.g. "b'\\x80\\x04...'"

        result = executor._deserialize_parameter_value(
            param_name="payload",
            param_value="uuid-1",
            unique_uuid_to_values={"uuid-1": pickled_repr},
        )

        assert result == original

    def test_returns_original_string_when_eval_fails(self) -> None:
        executor = _make_executor()

        result = executor._deserialize_parameter_value(
            param_name="payload",
            param_value="uuid-1",
            unique_uuid_to_values={"uuid-1": "not a bytes literal"},
        )

        assert result == "not a bytes literal"

    def test_returns_original_string_when_eval_yields_non_bytes(self) -> None:
        """If literal_eval returns something that isn't bytes, fall through to the string."""
        executor = _make_executor()

        result = executor._deserialize_parameter_value(
            param_name="payload",
            param_value="uuid-1",
            # "[1, 2, 3]" evals to a list, not bytes
            unique_uuid_to_values={"uuid-1": "[1, 2, 3]"},
        )

        assert result == "[1, 2, 3]"

    def test_returns_original_string_when_unpickle_fails(self) -> None:
        executor = _make_executor()
        # Valid bytes literal but not a valid pickle stream.
        bogus = repr(b"\x99garbage\x00")

        result = executor._deserialize_parameter_value(
            param_name="payload",
            param_value="uuid-1",
            unique_uuid_to_values={"uuid-1": bogus},
        )

        assert result == bogus


class TestExtractParameterOutputValues:
    """_extract_parameter_output_values merges per-node outputs from a subprocess result."""

    def test_returns_empty_dict_for_empty_input(self) -> None:
        assert _make_executor()._extract_parameter_output_values({}) == {}

    def test_passes_through_values_when_no_uuid_mapping(self) -> None:
        executor = _make_executor()
        subprocess_result: dict[str, Any] = {
            "node_a": {"parameter_output_values": {"out1": 1, "out2": "two"}},
        }

        assert executor._extract_parameter_output_values(subprocess_result) == {"out1": 1, "out2": "two"}

    def test_deserializes_uuid_referenced_values(self) -> None:
        executor = _make_executor()
        original = [10, 20, 30]
        pickled_repr = repr(pickle.dumps(original))
        subprocess_result: dict[str, Any] = {
            "node_a": {
                "parameter_output_values": {"items": "uuid-1"},
                "unique_parameter_uuid_to_values": {"uuid-1": pickled_repr},
            },
        }

        assert executor._extract_parameter_output_values(subprocess_result) == {"items": original}

    def test_merges_outputs_from_multiple_result_dicts(self) -> None:
        executor = _make_executor()
        subprocess_result: dict[str, Any] = {
            "node_a": {"parameter_output_values": {"a": 1}},
            "node_b": {"parameter_output_values": {"b": 2}},
        }

        assert executor._extract_parameter_output_values(subprocess_result) == {"a": 1, "b": 2}

    def test_backward_compatible_with_flat_result_shape(self) -> None:
        """Old flat structure: result dict directly contains output keys."""
        executor = _make_executor()
        subprocess_result: dict[str, Any] = {
            "node_a": {"out1": "hello", "out2": "world"},
        }

        assert executor._extract_parameter_output_values(subprocess_result) == {"out1": "hello", "out2": "world"}


class TestExecuteSubflowNodeGroupBranches:
    """SubflowNodeGroup non-local branches delegate to dedicated workflow paths."""

    @pytest.mark.asyncio
    async def test_private_execution_calls_private_workflow_path(self) -> None:
        node = _make_subflow_node(PRIVATE_EXECUTION)

        with (
            patch(_GRIPTAPE_NODES_PATH) as mock_gn,
            patch.object(NodeExecutor, "_execute_private_workflow", new_callable=AsyncMock) as mock_private,
            patch.object(NodeExecutor, "_execute_library_workflow", new_callable=AsyncMock) as mock_library,
        ):
            mock_gn.ahandle_request = AsyncMock()
            await _make_executor().execute(node)

        mock_private.assert_awaited_once_with(node)
        mock_library.assert_not_awaited()
        node.aprocess.assert_not_awaited()
        mock_gn.ahandle_request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_library_execution_routes_through_library_workflow(self) -> None:
        """A non-Local, non-Private execution_environment is treated as a library name."""
        node = _make_subflow_node("some_library_name")

        with (
            patch(_GRIPTAPE_NODES_PATH) as mock_gn,
            patch.object(NodeExecutor, "_execute_private_workflow", new_callable=AsyncMock) as mock_private,
            patch.object(NodeExecutor, "_execute_library_workflow", new_callable=AsyncMock) as mock_library,
        ):
            mock_gn.ahandle_request = AsyncMock()
            await _make_executor().execute(node)

        mock_library.assert_awaited_once_with(node, "some_library_name")
        mock_private.assert_not_awaited()
        node.aprocess.assert_not_awaited()
        mock_gn.ahandle_request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_subprocess_paths_clear_execution_state_first(self) -> None:
        """Both PRIVATE and library paths must clear execution state before running."""
        node = _make_subflow_node(PRIVATE_EXECUTION)

        with (
            patch(_GRIPTAPE_NODES_PATH),
            patch.object(NodeExecutor, "_execute_private_workflow", new_callable=AsyncMock),
        ):
            await _make_executor().execute(node)

        node.subflow_execution_component.clear_execution_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_local_execution_does_not_clear_execution_state(self) -> None:
        """LOCAL_EXECUTION runs aprocess directly; clearing subprocess state is unnecessary."""
        node = _make_subflow_node(LOCAL_EXECUTION)

        with patch(_GRIPTAPE_NODES_PATH):
            await _make_executor().execute(node)

        node.subflow_execution_component.clear_execution_state.assert_not_called()


class TestExecuteUnexpectedResultType:
    """Anything that isn't an ExecuteNodeResultSuccess is surfaced as a RuntimeError."""

    @pytest.mark.asyncio
    async def test_raises_when_result_is_not_a_success_payload(self) -> None:
        node = MagicMock()
        node.name = "Weird"
        node.parameter_values = {}
        node.parameter_output_values = {}
        node.metadata = {}

        not_a_payload: Any = "not a payload at all"

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.ahandle_request = AsyncMock(return_value=not_a_payload)

            with pytest.raises(RuntimeError, match="Weird"):
                await _make_executor().execute(node)


class TestExecuteSuccessReturnsNone:
    """The contract of execute() is to return None; all output flows via parameter_output_values."""

    @pytest.mark.asyncio
    async def test_returns_none_on_success(self) -> None:
        node = MagicMock()
        node.name = "Plain"
        node.parameter_values = {}
        node.parameter_output_values = {}
        node.metadata = {}

        with patch(_GRIPTAPE_NODES_PATH) as mock_gn:
            mock_gn.ahandle_request = AsyncMock(
                return_value=ExecuteNodeResultSuccess(result_details="ok", parameter_output_values={"x": 1}),
            )
            result = await _make_executor().execute(node)

        assert result is None
