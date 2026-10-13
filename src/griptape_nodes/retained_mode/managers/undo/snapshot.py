from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple

from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_groups.base_node_group import BaseNodeGroup
from griptape_nodes.retained_mode.events.node_events import (
    SerializedParameterValueTracker,
    SerializeNodeToCommandsRequest,
    SerializeNodeToCommandsResultSuccess,
)

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode, Connection
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.node_events import SerializedNodeCommands

logger = logging.getLogger("griptape_nodes")

# Metadata that follows from something else rather than from an edit. Library details come from the
# node's library, and the editor writes them back with every move. Membership and subflow bookkeeping
# follow the group requests undo issues, so restoring them as plain metadata would fight those requests.
MANAGED_METADATA_KEYS = frozenset(
    {
        "category",
        "executable",
        "is_node_group",
        "library",
        "library_node_metadata",
        "node_names_in_group",
        "node_type",
        "subflow_name",
    }
)

# Parts of an element's description that change without its structure changing.
_VOLATILE_ELEMENT_KEYS = frozenset({"element_id", "badge"})


class ConnectionKey(NamedTuple):
    source_node: str
    source_parameter: str
    target_node: str
    target_parameter: str


@dataclass(frozen=True)
class NodeImage:
    name: str
    node_type: str
    flow_name: str | None
    parent_group: str | None
    is_group: bool
    members: tuple[str, ...]
    metadata: dict[str, Any]
    lock: bool
    # Parameter names retain node order.
    parameters: tuple[str, ...]
    values: dict[str, SerializedNodeCommands.UniqueParameterValueUUID]
    # A parameter listed here but missing from `values` has an unsavable value.
    explicit_values: frozenset[str]
    structure: str
    connections: frozenset[ConnectionKey]
    commands: SerializedNodeCommands = field(repr=False)
    value_commands: list[SerializedNodeCommands.IndirectSetParameterValueCommand] = field(repr=False)
    value_pool: dict[SerializedNodeCommands.UniqueParameterValueUUID, Any] = field(repr=False)

    def same_state(self, other: NodeImage) -> bool:
        return (
            self.name == other.name
            and self.flow_name == other.flow_name
            and self.parent_group == other.parent_group
            and self.members == other.members
            and self.lock == other.lock
            # Content hashes compare values by content even when each capture encodes afresh.
            and self.values == other.values
            and self.structure == other.structure
            and _values_equal(self.metadata, other.metadata)
        )

    def changed_metadata_keys(self, other: NodeImage) -> set[str]:
        keys = set(self.metadata) | set(other.metadata)
        return {key for key in keys if not _values_equal(self.metadata.get(key), other.metadata.get(key))}

    def changed_values(self, other: NodeImage) -> set[str]:
        parameters = set(self.values) | set(other.values)
        return {name for name in parameters if self.values.get(name) != other.values.get(name)}


def capture_node(engine: Engine, node: BaseNode) -> NodeImage | None:
    """Image a live node, or None when it cannot be serialized right now.

    Never raises: capture runs before a client's request is handled, and a node that will not
    serialize must leave that edit unrecorded rather than fail it.
    """
    flow_name = _parent_flow_name(engine, node)
    if flow_name is None:
        return None
    flow = engine.object_manager.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
    if flow is None or not engine.context_manager.has_current_workflow():
        return None

    value_pool: dict[SerializedNodeCommands.UniqueParameterValueUUID, Any] = {}
    request = SerializeNodeToCommandsRequest(
        node_name=node.name,
        unique_parameter_uuid_to_values=value_pool,
        serialized_parameter_value_tracker=SerializedParameterValueTracker(),
    )
    try:
        with engine.context_manager.flow(flow):
            result = engine.node_manager.on_serialize_node_to_commands(request)
    except Exception:
        logger.exception("Undo could not record Node '%s'. Changes to it in this edit cannot be undone.", node.name)
        return None
    if not isinstance(result, SerializeNodeToCommandsResultSuccess):
        logger.debug("Undo could not record Node '%s': %s", node.name, result.result_details)
        return None

    commands = result.serialized_node_commands
    value_commands = list(result.set_parameter_value_commands)
    values = {
        command.set_parameter_value_command.parameter_name: command.unique_value_uuid
        for command in value_commands
        if not command.set_parameter_value_command.is_output
    }
    metadata = {key: copy.deepcopy(value) for key, value in node.metadata.items() if key not in MANAGED_METADATA_KEYS}
    parent_group = node.parent_group.name if node.parent_group is not None else None
    members = tuple(sorted(node.nodes)) if isinstance(node, BaseNodeGroup) else ()

    return NodeImage(
        name=node.name,
        node_type=type(node).__name__,
        flow_name=flow_name,
        parent_group=parent_group,
        is_group=isinstance(node, BaseNodeGroup),
        members=members,
        metadata=metadata,
        lock=bool(node.lock),
        parameters=tuple(parameter.name for parameter in node.parameters),
        values=values,
        explicit_values=frozenset(node.parameter_values.keys()),
        structure=_structure_text(node),
        connections=frozenset(connection_key(connection) for connection in incident_connections(engine, node)),
        commands=commands,
        value_commands=value_commands,
        value_pool=value_pool,
    )


def incident_connections(engine: Engine, node: BaseNode) -> list[Connection]:
    """Every connection into or out of a node."""
    connections = engine.flow_manager.get_connections()
    found: list[Connection] = []
    for index in (connections.incoming_index, connections.outgoing_index):
        for connection_ids in index.get(node.name, {}).values():
            for connection_id in connection_ids:
                connection = connections.connections.get(connection_id)
                if connection is not None:
                    found.append(connection)
    return found


def connection_key(connection: Connection) -> ConnectionKey:
    """A connection by the current names of its endpoints."""
    return ConnectionKey(
        source_node=connection.source_node.name,
        source_parameter=connection.source_parameter.name,
        target_node=connection.target_node.name,
        target_parameter=connection.target_parameter.name,
    )


def is_live(engine: Engine, node: BaseNode) -> bool:
    """Whether a node object is still part of the workflow."""
    return engine.object_manager.attempt_get_object_by_name(node.name) is node


def _parent_flow_name(engine: Engine, node: BaseNode) -> str | None:
    try:
        return engine.node_manager.get_node_parent_flow_by_name(node.name)
    except KeyError:
        return None


def _structure_text(node: BaseNode) -> str:
    """The node's parameter structure as text that is equal exactly when the structure is.

    Read from the node itself rather than from the serialized commands: those describe how the node
    differs from a freshly built copy, and that comparison does not always come out the same way
    twice. Element ids are random per construction and badges report status rather than structure,
    so both are left out.
    """
    return json.dumps(_without_volatile_keys(node.root_ui_element.to_dict()), sort_keys=True, default=repr)


def _without_volatile_keys(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: _without_volatile_keys(value) for key, value in data.items() if key not in _VOLATILE_ELEMENT_KEYS}
    if isinstance(data, list):
        return [_without_volatile_keys(item) for item in data]
    return data


def _values_equal(left: Any, right: Any) -> bool:
    try:
        return bool(left == right)
    except Exception:
        return False
