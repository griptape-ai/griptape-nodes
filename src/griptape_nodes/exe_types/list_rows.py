"""Keeps a node's list parameters and their rows in step.

A list nothing is connected to holds its items in rows, one child parameter per item. Its own entry in
`parameter_values` is built from those rows, and is what execution, saving and `GetParameterValueRequest`
read, so every edit to the rows stores it again.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from packaging.version import InvalidVersion
from packaging.version import Version as PackagingVersion

from griptape_nodes.exe_types.core_types import Parameter, ParameterContainer, ParameterList, ParameterMode
from griptape_nodes.exe_types.parameter_mutation import sanctioned_parameter_mutation
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.retained_mode.events.connection_events import (
    ListConnectionsForNodeRequest,
    ListConnectionsForNodeResultSuccess,
)

if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import BaseNodeElement
    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")

# A library declaring this engine version or later has a whole list its nodes write become the list's rows.
LIST_WRITES_FILL_ROWS_ENGINE_VERSION = PackagingVersion("0.105.0")


class ListRows:
    """The rows of one node's lists: replacing them, and storing each list again when they change."""

    def __init__(self, node: BaseNode) -> None:
        self._node = node
        # Lists whose rows `_replace` is replacing. They are stored once, when every row is in place.
        self._being_replaced: set[str] = set()

    def set_as_rows_if_unconnected(self, parameter: Parameter, value: Any) -> bool:
        """Write a whole list to the rows of an unconnected list. Returns whether it did.

        The engine calls this where a value arrives from outside the node: a request, and a worker
        copy receiving the list it runs with. An unconnected list is read from its rows, so a list
        stored beside them would never be read.

        Raises:
            TypeError: if `value` is not a list.
            ValueError: if there are more items than `max_items`, or a row is connected to another node.
        """
        if not isinstance(parameter, ParameterList) or value is None:
            # None is how a value is cleared, and keeps its old meaning.
            return False
        modes = parameter.allowed_modes
        if ParameterMode.INPUT not in modes and ParameterMode.PROPERTY not in modes:
            # An output-only list is built by its own node, row by row.
            return False
        if isinstance(value, list) and value == handle_container_parameter(self._node, parameter):
            # Already what the rows hold.
            return False
        if parameter.name in self._being_replaced:
            # Storing it would leave the list's value and its rows disagreeing, and replacing the rows
            # again would undo the rows being set.
            logger.warning(
                "Node '%s' set list '%s' while its items were being set, so the write was ignored. "
                "Convert each item with the list's item_converters instead.",
                self._node.name,
                parameter.name,
            )
            return True
        if self._node._param_has_incoming_connection(parameter.name):
            # A connected list is read whole, and keeps the value as it arrived.
            return False
        self._replace(parameter, value)
        return True

    def row_removed(self, parameter_list: ParameterList, row: BaseNodeElement) -> None:
        """Drop a removed row's value, and take it out of the list."""
        self._node.parameter_values.pop(row.name, None)
        self.rebuild(parameter_list)

    def rebuild(self, container: ParameterContainer, *, initial_setup: bool = False) -> None:
        """Store a container's value again, built from its rows, after a row is set, removed or moved."""
        if container.name in self._being_replaced:
            return
        if ParameterMode.INPUT in container.allowed_modes and self._node._param_has_incoming_connection(container.name):
            # A connected list holds the value its connection delivered.
            return
        self._store(container, initial_setup=initial_setup)

    def values_for_dispatch(self) -> dict[str, Any]:
        """`parameter_values`, with each list as the node reads it and without its rows, to send with `ExecuteNodeRequest`.

        A worker copy has no rows and builds its own, with new names, from the list. A list's own entry
        can still hold items whose rows were removed, in a workflow saved before the entry followed its
        rows.
        """
        node = self._node
        values = dict(node.parameter_values)
        for parameter in node.parameters:
            if not isinstance(parameter, ParameterList):
                continue
            rows = parameter.get_child_parameters()
            if parameter.name not in values and not rows:
                continue
            values[parameter.name] = node._get_raw_parameter_value(parameter.name)
            for row in rows:
                values.pop(row.name, None)
        return values

    def _replace(self, parameter_list: ParameterList, items: Any) -> None:
        """Replace the list's rows with one row per item, the way the editor fills a list.

        Each row is set through `set_parameter_value`, so the node's hooks fire for each one. If an item
        is rejected, the old rows are put back and the error is raised.

        Raises:
            TypeError: if `items` is not a list.
            ValueError: if there are more items than `max_items`, or a row is connected to another node.
        """
        node = self._node
        list_label = f"'{node.name}.{parameter_list.name}'"
        if not isinstance(items, list):
            msg = f"Attempted to set list {list_label}. Failed because a list can only be set to a list, but got a value of type '{type(items).__name__}'."
            raise TypeError(msg)
        max_items = parameter_list.max_items
        if max_items is not None and len(items) > max_items:
            msg = f"Attempted to set list {list_label} to {len(items)} items. Failed because the list holds at most {max_items} items."
            raise ValueError(msg)
        old_rows = parameter_list.get_child_parameters()
        # Checked only when there are rows: on a worker the question goes to the orchestrator.
        if old_rows and self._connected_parameter_names({row.name for row in old_rows}):
            msg = f"Attempted to set list {list_label}. Failed because some of its items are connected to other nodes, and replacing the items would remove those connections. Disconnect them first."
            raise ValueError(msg)

        old_values = {
            row.name: node.parameter_values[row.name] for row in old_rows if row.name in node.parameter_values
        }
        self._being_replaced.add(parameter_list.name)
        try:
            with sanctioned_parameter_mutation():
                for row in old_rows:
                    node.remove_parameter_element(row)
            for item in items:
                row = parameter_list.add_child_parameter()
                node.set_parameter_value(row.name, item)
            self._store(parameter_list, initial_setup=False)
        except Exception:
            # Converters, validators and hooks may raise anything. Undo, then let it propagate unchanged.
            self._restore(parameter_list, old_rows, old_values)
            raise
        finally:
            self._being_replaced.discard(parameter_list.name)

    def _restore(self, parameter_list: ParameterList, rows: list[Parameter], values: dict[str, Any]) -> None:
        """Put back the rows `_replace` removed, with their values, and remove the ones it added."""
        node = self._node
        with sanctioned_parameter_mutation():
            for row in parameter_list.get_child_parameters():
                node.remove_parameter_element(row)
        for row in rows:
            parameter_list.add_child(row)
        node.parameter_values.update(values)
        # Written without running hooks, which could raise again and hide the error being undone.
        node.parameter_values[parameter_list.name] = handle_container_parameter(node, parameter_list)

    def _store(self, container: ParameterContainer, *, initial_setup: bool) -> None:
        """Build a container's value from its rows and store it, running what a set of that value would.

        Its converters, validators and hooks run, but not a list's item converters: the rows ran those.
        """
        node = self._node
        value = handle_container_parameter(node, container)
        for converter in container.converters:
            value = converter(value)
        for validator in container.validators:
            validator(container, value)
        if not initial_setup:
            value = node.before_value_set(parameter=container, value=value)
        node.parameter_values[container.name] = value
        node._also_record_as_result(container, value)
        if not initial_setup:
            node.after_value_set(parameter=container, value=value)

    def _connected_parameter_names(self, parameter_names: set[str]) -> set[str]:
        """Which of `parameter_names` have a connection in either direction."""
        node = self._node
        result = node.engine.handle_request(ListConnectionsForNodeRequest(node_name=node.name, broadcast_result=False))
        if not isinstance(result, ListConnectionsForNodeResultSuccess):
            return set()
        connected = {connection.target_parameter_name for connection in result.incoming_connections}
        connected.update(connection.source_parameter_name for connection in result.outgoing_connections)
        return connected & parameter_names


def library_fills_list_rows(library_name: str | None) -> bool:
    """Whether a library declares an engine version where a whole list its nodes write fills the rows."""
    if not library_name:
        return False
    try:
        library = LibraryRegistry.get_library(library_name)
    except KeyError:
        return False
    try:
        declared = PackagingVersion(library.get_metadata().engine_version)
    except InvalidVersion:
        return False
    return declared >= LIST_WRITES_FILL_ROWS_ENGINE_VERSION


def handle_container_parameter(current_node: BaseNode, parameter: Parameter) -> list[Any] | None:
    """Build a container's value from its rows, or None if `parameter` is not a container."""
    if not isinstance(parameter, ParameterContainer):
        return None
    build_parameter_value = []
    for child in parameter.find_elements_by_type(Parameter, find_recursively=False):
        # Raw, because what this builds is cached into the container's own entry in
        # `parameter_values`, and that dict is the payload of an ExecuteNodeRequest. Translating here
        # would put a live object in it and send it to a worker as JSON. The node still sees objects:
        # its read resolves the whole list on the way out.
        value = current_node._get_raw_parameter_value(child.name)
        if value is not None:
            build_parameter_value.append(value)
    return build_parameter_value
