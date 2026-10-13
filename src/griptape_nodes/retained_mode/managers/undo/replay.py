"""Moving the workflow from one side of a history entry to the other, through ordinary requests.

Replay issues the same requests a person would, so every manager keeps its own invariants and the
editor updates through the results it already handles. Each phase reads the workflow as it is
rather than trusting the entry, because restoring one thing often restores another along with it:
taking a node out of a group, for example, rewires its connections back on its own. Group
membership is restored before connections for that reason, and connections before values, since
connecting a parameter overwrites its value.

A part that cannot be restored is reported and skipped. The rest still applies, so one stale node
does not cost the whole step.
"""

from __future__ import annotations

import copy
import logging
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from griptape_nodes.exe_types.node_groups.base_node_group import BaseNodeGroup
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.events.connection_events import CreateConnectionRequest, DeleteConnectionRequest
from griptape_nodes.retained_mode.events.node_events import (
    AddNodesToNodeGroupRequest,
    DeleteNodeRequest,
    DeserializeNodeFromCommandsRequest,
    DeserializeNodeFromCommandsResultSuccess,
    MoveNodeToNewFlowRequest,
    RemoveNodeFromNodeGroupRequest,
    SetLockNodeStateRequest,
    SetNodeMetadataRequest,
)
from griptape_nodes.retained_mode.events.object_events import RenameObjectRequest
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.managers.undo.snapshot import capture_node, connection_key, incident_connections
from griptape_nodes.serialization.values import decode_value

if TYPE_CHECKING:
    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import RequestPayload
    from griptape_nodes.retained_mode.managers.undo.history import HistoryEntry
    from griptape_nodes.retained_mode.managers.undo.snapshot import ConnectionKey, NodeImage

logger = logging.getLogger("griptape_nodes")


class Direction(Enum):
    UNDO = auto()
    REDO = auto()


def replay(engine: Engine, entry: HistoryEntry, direction: Direction) -> list[str]:
    """Return a sentence for each part that could not be restored."""
    return _Replay(engine, entry, direction).run()


class _Replay:
    def __init__(self, engine: Engine, entry: HistoryEntry, direction: Direction) -> None:
        self._engine = engine
        self._problems: list[str] = []
        # Source is the side the workflow is on now, target the side to move it to.
        if direction is Direction.UNDO:
            self._pairs = [(change.after, change.before) for change in entry.changes]
            self._stale_connections = entry.connections_added
            self._missing_connections = entry.connections_removed
        else:
            self._pairs = [(change.before, change.after) for change in entry.changes]
            self._stale_connections = entry.connections_removed
            self._missing_connections = entry.connections_added

    def run(self) -> list[str]:
        removed = [source for source, target in self._pairs if target is None and source is not None]
        added = [target for source, target in self._pairs if source is None and target is not None]
        kept = [(source, target) for source, target in self._pairs if source is not None and target is not None]

        self._leave_groups(kept)
        self._remove_connections()
        self._delete_nodes(removed)
        self._rename_nodes(kept)
        self._create_nodes(added)
        self._join_groups(kept, added)
        self._move_between_flows(kept)
        self._add_connections()
        # Connecting a parameter overwrites its value, so restore values afterwards.
        for source, target in kept:
            self._restore_properties(source, target)
        for source, target in kept:
            self._restore_structure(source, target)
        for target in added:
            self._restore_lock(target)
        return self._problems

    def _leave_groups(self, kept: list[tuple[NodeImage, NodeImage]]) -> None:
        """Take nodes out of groups they should not be in, before any connection is touched.

        A group rewires a member's connections back to their original endpoints as the member
        leaves, so this has to run while those connections are still the group's.
        """
        for member_name, group_name in self._memberships_to_leave(kept):
            group = self._node(group_name)
            if not isinstance(group, BaseNodeGroup) or member_name not in group.nodes:
                continue
            self._send(
                RemoveNodeFromNodeGroupRequest(
                    node_names=[member_name], node_group_name=group_name, flow_name=self._flow_of(group_name)
                ),
                f"Could not take '{member_name}' out of group '{group_name}'.",
            )

    def _remove_connections(self) -> None:
        for key in sorted(self._stale_connections):
            if not self._connection_exists(key):
                continue
            self._send(
                DeleteConnectionRequest(
                    source_node_name=key.source_node,
                    source_parameter_name=key.source_parameter,
                    target_node_name=key.target_node,
                    target_parameter_name=key.target_parameter,
                ),
                f"Could not remove the connection from '{key.source_node}' to '{key.target_node}'.",
            )

    def _delete_nodes(self, removed: list[NodeImage]) -> None:
        # Members before their groups, so a group never has to release a node that is going anyway.
        for source in sorted(removed, key=lambda image: image.is_group):
            if self._node(source.name) is None:
                continue
            self._send(DeleteNodeRequest(node_name=source.name), f"Could not delete '{source.name}'.")

    def _rename_nodes(self, kept: list[tuple[NodeImage, NodeImage]]) -> None:
        renames = [(source.name, target.name) for source, target in kept if source.name != target.name]
        # A name another renamed node still holds goes through a placeholder, so swapped or chained
        # names never collide.
        blocked = []
        for current_name, target_name in renames:
            if self._node(target_name) is None:
                self._rename(current_name, target_name)
            else:
                blocked.append((current_name, target_name))
        placeholders = []
        for index, (current_name, target_name) in enumerate(blocked):
            placeholder = f"{target_name}__undo_{index}"
            if self._rename(current_name, placeholder):
                placeholders.append((placeholder, target_name))
        for placeholder, target_name in placeholders:
            self._rename(placeholder, target_name)

    def _create_nodes(self, added: list[NodeImage]) -> None:
        # Groups first, outermost first, so each member's group exists when the member is created.
        for target in sorted(added, key=lambda image: (not image.is_group, image.parent_group is not None)):
            self._recreate(target)

    def _join_groups(self, kept: list[tuple[NodeImage, NodeImage]], added: list[NodeImage]) -> None:
        """Put nodes back into their groups, before connections come back.

        A member that joins a group with no connections leaves the group's parameters alone, so the
        connections restored next land on exactly the parameters they were recorded on.
        """
        for member_name, group_name in self._memberships_to_join(kept, added):
            group = self._node(group_name)
            member = self._node(member_name)
            if not isinstance(group, BaseNodeGroup) or member is None:
                continue
            if member_name in group.nodes and member.parent_group is group:
                continue
            self._send(
                AddNodesToNodeGroupRequest(
                    node_names=[member_name], node_group_name=group_name, flow_name=self._flow_of(group_name)
                ),
                f"Could not put '{member_name}' back into group '{group_name}'.",
            )

    def _move_between_flows(self, kept: list[tuple[NodeImage, NodeImage]]) -> None:
        for _source, target in kept:
            if target.parent_group is not None or target.flow_name is None:
                continue
            current_flow = self._flow_of(target.name)
            if current_flow is None or current_flow == target.flow_name:
                continue
            self._send(
                MoveNodeToNewFlowRequest(node_name=target.name, target_flow_name=target.flow_name),
                f"Could not move '{target.name}' back to flow '{target.flow_name}'.",
            )

    def _add_connections(self) -> None:
        for key in sorted(self._missing_connections):
            if self._connection_exists(key):
                continue
            if self._node(key.source_node) is None or self._node(key.target_node) is None:
                continue
            self._connect(key)

    def _restore_properties(self, source: NodeImage, target: NodeImage) -> None:
        node = self._node(target.name)
        if node is None:
            return

        changed_keys = source.changed_metadata_keys(target)
        if changed_keys:
            self._send(
                SetNodeMetadataRequest(
                    node_name=target.name,
                    metadata={
                        key: copy.deepcopy(target.metadata[key]) for key in changed_keys if key in target.metadata
                    },
                    keys_to_remove=sorted(key for key in changed_keys if key not in target.metadata),
                ),
                f"Could not restore how '{target.name}' is laid out.",
            )

        changed_values = source.changed_values(target)
        if changed_values:
            if node.lock:
                self._send(
                    SetLockNodeStateRequest(node_name=target.name, lock=False),
                    f"Could not unlock '{target.name}' to restore its values.",
                )
            self._restore_values(node, target, changed_values)

        self._restore_lock(target)

    def _restore_structure(self, source: NodeImage, target: NodeImage) -> None:
        """Rebuild a node whose parameters still differ from the target once its values are back.

        Values come back first, with the node's own hooks running, because most parameters a node
        adds, hides, or retypes follow from a value it was given. Only a node still out of shape after
        that is rebuilt. Groups are never rebuilt: their parameters follow their members and
        connections, which earlier phases already restored.
        """
        if source.structure == target.structure or target.is_group:
            return
        node = self._node(target.name)
        if node is None:
            return
        live = capture_node(self._engine, node)
        if live is None or live.structure == target.structure:
            return

        if not self._send(DeleteNodeRequest(node_name=target.name), f"Could not rebuild '{target.name}'."):
            return
        if not self._recreate(target):
            return
        for key in sorted(target.connections):
            if self._node(key.source_node) is None or self._node(key.target_node) is None:
                continue
            if not self._connection_exists(key):
                self._connect(key)
        self._restore_lock(target)

    def _recreate(self, target: NodeImage) -> bool:
        commands = copy.deepcopy(target.commands)
        create = commands.create_node_command
        create.node_name = target.name
        # Members rejoin their group in a later phase, once every member exists.
        create.node_names_to_add = None
        create.set_as_new_context = False
        if target.parent_group is not None and self._node(target.parent_group) is not None:
            create.parent_group_name = target.parent_group
            create.override_parent_flow_name = self._flow_of(target.parent_group)
        else:
            create.parent_group_name = None
            create.override_parent_flow_name = target.flow_name

        result = self._engine.handle_request(DeserializeNodeFromCommandsRequest(serialized_node_commands=commands))
        if not isinstance(result, DeserializeNodeFromCommandsResultSuccess):
            self._problems.append(f"Could not bring back '{target.name}'.")
            return False
        if result.node_name != target.name:
            self._problems.append(f"Brought back '{target.name}' as '{result.node_name}', because the name is taken.")

        for value_command in target.value_commands:
            request = copy.deepcopy(value_command.set_parameter_value_command)
            request.node_name = result.node_name
            request.value = decode_value(target.value_pool[value_command.unique_value_uuid])
            self._send(request, f"Could not restore '{request.parameter_name}' on '{result.node_name}'.")
        return True

    def _restore_values(self, node: BaseNode, target: NodeImage, parameters: set[str]) -> None:
        """Set parameters back to the target's values.

        The first pass sets each value the way a person would, so the node's hooks rebuild whatever
        follows from it and the node is marked for a re-run. The second pass sets any value still
        off target directly, without hooks, the way loading a workflow does.
        """
        connections = self._engine.flow_manager.get_connections()
        connected = set(connections.incoming_index.get(node.name, {}))
        # A parameter missing on either side comes back with the node's structure instead.
        restorable = [
            parameter
            for name in sorted(parameters)
            if name in target.parameters
            and (parameter := node.get_parameter_by_name(name)) is not None
            and self._has_target_value(target, name)
        ]

        for parameter in restorable:
            if parameter.name in connected:
                continue
            self._engine.handle_request(
                SetParameterValueRequest(
                    node_name=node.name,
                    parameter_name=parameter.name,
                    value=self._target_value(parameter, target),
                    failure_log_level=logging.DEBUG,
                )
            )

        live = capture_node(self._engine, node)
        for parameter in restorable:
            if live is not None and live.values.get(parameter.name) == target.values.get(parameter.name):
                continue
            self._send(
                SetParameterValueRequest(
                    node_name=node.name,
                    parameter_name=parameter.name,
                    value=self._target_value(parameter, target),
                    initial_setup=True,
                ),
                f"Could not restore '{parameter.name}' on '{node.name}'.",
            )

    def _restore_lock(self, target: NodeImage) -> None:
        node = self._node(target.name)
        if node is None or bool(node.lock) == target.lock:
            return
        self._send(
            SetLockNodeStateRequest(node_name=target.name, lock=target.lock),
            f"Could not {'lock' if target.lock else 'unlock'} '{target.name}'.",
        )

    def _connect(self, key: ConnectionKey) -> None:
        self._send(
            CreateConnectionRequest(
                source_node_name=key.source_node,
                source_parameter_name=key.source_parameter,
                target_node_name=key.target_node,
                target_parameter_name=key.target_parameter,
            ),
            f"Could not reconnect '{key.source_node}' to '{key.target_node}'.",
        )

    def _rename(self, current_name: str, requested_name: str) -> bool:
        return self._send(
            RenameObjectRequest(object_name=current_name, requested_name=requested_name),
            f"Could not rename '{current_name}' back to '{requested_name}'.",
        )

    def _send(self, request: RequestPayload, problem: str) -> bool:
        """Use ordinary requests to preserve manager invariants and notify the editor."""
        result = self._engine.handle_request(request)
        if result.succeeded():
            return True
        logger.debug("Undo step failed: %s %s", problem, result.result_details)
        self._problems.append(problem)
        return False

    def _node(self, name: str) -> BaseNode | None:
        return self._engine.object_manager.attempt_get_object_by_name_as_type(name, BaseNode)

    def _flow_of(self, node_name: str) -> str | None:
        try:
            return self._engine.node_manager.get_node_parent_flow_by_name(node_name)
        except KeyError:
            return None

    def _connection_exists(self, key: ConnectionKey) -> bool:
        node = self._node(key.source_node)
        if node is None:
            return False
        return any(connection_key(connection) == key for connection in incident_connections(self._engine, node))

    @staticmethod
    def _memberships_to_leave(kept: list[tuple[NodeImage, NodeImage]]) -> list[tuple[str, str]]:
        """(member, group) pairs that hold now but not on the target side, by current names."""
        pairs: dict[tuple[str, str], None] = {}
        for source, target in kept:
            if source.parent_group is not None and source.parent_group != target.parent_group:
                pairs[(source.name, source.parent_group)] = None
            for member_name in set(source.members) - set(target.members):
                pairs[(member_name, source.name)] = None
        return list(pairs)

    @staticmethod
    def _memberships_to_join(kept: list[tuple[NodeImage, NodeImage]], added: list[NodeImage]) -> list[tuple[str, str]]:
        """(member, group) pairs the target side holds, by target names."""
        pairs: dict[tuple[str, str], None] = {}
        for _source, target in kept:
            if target.parent_group is not None:
                pairs[(target.name, target.parent_group)] = None
            for member_name in target.members:
                pairs[(member_name, target.name)] = None
        for target in added:
            for member_name in target.members:
                pairs[(member_name, target.name)] = None
        return list(pairs)

    @staticmethod
    def _has_target_value(target: NodeImage, parameter_name: str) -> bool:
        """Whether the target's value for a parameter is known: saved, or never set."""
        return parameter_name in target.values or parameter_name not in target.explicit_values

    @staticmethod
    def _target_value(parameter: Parameter, target: NodeImage) -> Any:
        unique_value_uuid = target.values.get(parameter.name)
        if unique_value_uuid is not None:
            return decode_value(target.value_pool[unique_value_uuid])
        return parameter.default_value
