"""The structural changes an edit makes to a workflow, each able to reverse and re-apply itself.

A manager makes one of these with `journal.apply`, which calls `make`, so the change is carried out
by the same manager method whether it is being made, undone, or redone. Undo and redo first ask
`needed`, which is False when the workflow is already where the step leads and raises
`journal.Conflict` when something outside the history has made the step impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.journal import STALE, Conflict, Structural

if TYPE_CHECKING:
    from griptape_nodes.exe_types.connections import Connection, Connections, ConnectionSlot
    from griptape_nodes.exe_types.core_types import Parameter
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.exe_types.node_groups.base_node_group import BaseNodeGroup
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.retained_mode.managers.object_manager import ObjectManager


@dataclass(frozen=True, slots=True)
class NodeAdded(Structural):
    node: BaseNode
    flow_name: str

    def make(self) -> None:
        self.node.engine.node_manager.register_node(self.node, self.flow_name)

    def unmake(self) -> None:
        self.node.engine.node_manager.unregister_node(self.node)

    def needed(self, *, undoing: bool) -> bool:
        return _node_presence_needed(self.node, self.flow_name, present=not undoing)


@dataclass(frozen=True, slots=True)
class NodeRemoved(Structural):
    node: BaseNode
    flow_name: str

    def make(self) -> None:
        self.node.engine.node_manager.unregister_node(self.node)

    def unmake(self) -> None:
        self.node.engine.node_manager.register_node(self.node, self.flow_name)

    def needed(self, *, undoing: bool) -> bool:
        return _node_presence_needed(self.node, self.flow_name, present=undoing)


@dataclass(frozen=True, slots=True)
class NodeMoved(Structural):
    """A node moved from one flow to another, such as into a group's subflow."""

    node: BaseNode
    old_flow_name: str
    new_flow_name: str

    def make(self) -> None:
        self.node.engine.node_manager.move_node_to_flow(self.node, self.new_flow_name)

    def unmake(self) -> None:
        self.node.engine.node_manager.move_node_to_flow(self.node, self.old_flow_name)

    def needed(self, *, undoing: bool) -> bool:
        node = self.node
        if not is_live(node):
            msg = f"'{node.name}' no longer exists, so it cannot be moved."
            raise Conflict(msg)
        source, destination = _sides(self.old_flow_name, self.new_flow_name, undoing=undoing)
        current = node.engine.node_manager.get_node_parent_flow_by_name(node.name)
        if current == destination:
            return False
        if current != source:
            raise Conflict(STALE)
        if node.engine.object_manager.attempt_get_object_by_name(destination) is None:
            msg = f"'{destination}' no longer exists, so '{node.name}' cannot go back into it."
            raise Conflict(msg)
        return True


@dataclass(frozen=True, slots=True)
class ObjectRenamed(Structural):
    """A node or flow renamed."""

    objects: ObjectManager
    target: BaseNode | ControlFlow
    old_name: str
    new_name: str

    def make(self) -> None:
        self.objects.rename_object(self.old_name, self.new_name)

    def unmake(self) -> None:
        self.objects.rename_object(self.new_name, self.old_name)

    def needed(self, *, undoing: bool) -> bool:
        source, destination = _sides(self.old_name, self.new_name, undoing=undoing)
        # Already renamed, or deleted some other way since.
        if self.objects.attempt_get_object_by_name(source) is not self.target:
            return False
        if self.objects.has_object_with_name(destination):
            raise Conflict(STALE)
        return True


@dataclass(frozen=True, slots=True)
class FlowAdded(Structural):
    flow: ControlFlow
    parent_name: str | None
    referenced_workflow_name: str | None

    def make(self) -> None:
        self.flow.engine.flow_manager.register_flow(self.flow, self.parent_name, self.referenced_workflow_name)

    def unmake(self) -> None:
        self.flow.engine.flow_manager.unregister_flow(self.flow)

    def needed(self, *, undoing: bool) -> bool:
        return _flow_presence_needed(self.flow, present=not undoing)


@dataclass(frozen=True, slots=True)
class FlowRemoved(Structural):
    flow: ControlFlow
    parent_name: str | None
    referenced_workflow_name: str | None

    def make(self) -> None:
        self.flow.engine.flow_manager.unregister_flow(self.flow)

    def unmake(self) -> None:
        self.flow.engine.flow_manager.register_flow(self.flow, self.parent_name, self.referenced_workflow_name)

    def needed(self, *, undoing: bool) -> bool:
        return _flow_presence_needed(self.flow, present=undoing)


@dataclass(frozen=True, slots=True)
class FlowReparented(Structural):
    flow: ControlFlow
    old_parent_name: str | None
    new_parent_name: str | None

    def make(self) -> None:
        self.flow.engine.flow_manager.set_flow_parent(self.flow.name, self.new_parent_name)

    def unmake(self) -> None:
        self.flow.engine.flow_manager.set_flow_parent(self.flow.name, self.old_parent_name)

    def needed(self, *, undoing: bool) -> bool:
        if not is_live(self.flow):
            return False
        source, destination = _sides(self.old_parent_name, self.new_parent_name, undoing=undoing)
        current = self.flow.engine.flow_manager.get_parent_flow(self.flow.name)
        if current == destination:
            return False
        if current != source:
            raise Conflict(STALE)
        return True


@dataclass(frozen=True, slots=True)
class ConnectionAdded(Structural):
    connections: Connections
    connection: Connection

    def make(self) -> None:
        self.connections.link(self.connection)

    def unmake(self) -> None:
        self.connections.unlink(self.connection)

    def needed(self, *, undoing: bool) -> bool:
        return _connection_presence_needed(self.connections, self.connection, present=not undoing)


@dataclass(frozen=True, slots=True)
class ConnectionRemoved(Structural):
    connections: Connections
    connection: Connection
    # Where it sat among its parameters' connections, so undo puts it back in order.
    slot: ConnectionSlot

    def make(self) -> None:
        self.connections.unlink(self.connection)

    def unmake(self) -> None:
        self.connections.link(self.connection, self.slot)

    def needed(self, *, undoing: bool) -> bool:
        return _connection_presence_needed(self.connections, self.connection, present=undoing)


@dataclass(frozen=True, slots=True)
class ParameterRenamed(Structural):
    node: BaseNode
    parameter: Parameter
    old_name: str
    new_name: str

    def make(self) -> None:
        self.node.engine.node_manager.rename_parameter(self.node, self.parameter, self.new_name)

    def unmake(self) -> None:
        self.node.engine.node_manager.rename_parameter(self.node, self.parameter, self.old_name)

    def needed(self, *, undoing: bool) -> bool:
        source, destination = _sides(self.old_name, self.new_name, undoing=undoing)
        if self.parameter.name == destination:
            return False
        if self.parameter.name != source or self.node.does_name_exist(destination):
            raise Conflict(STALE)
        return True


@dataclass(frozen=True, slots=True)
class GroupMemberAdded(Structural):
    group: BaseNodeGroup
    node: BaseNode

    def make(self) -> None:
        self.group.add_member(self.node)

    def unmake(self) -> None:
        self.group.remove_member(self.node)

    def needed(self, *, undoing: bool) -> bool:
        return _membership_needed(self.group, self.node, member=not undoing)


@dataclass(frozen=True, slots=True)
class GroupMemberRemoved(Structural):
    group: BaseNodeGroup
    node: BaseNode

    def make(self) -> None:
        self.group.remove_member(self.node)

    def unmake(self) -> None:
        self.group.add_member(self.node)

    def needed(self, *, undoing: bool) -> bool:
        return _membership_needed(self.group, self.node, member=undoing)


@dataclass(frozen=True, slots=True)
class LockChanged(Structural):
    node: BaseNode
    old: bool
    new: bool

    def make(self) -> None:
        self.node.engine.node_manager.set_lock(self.node, lock=self.new)

    def unmake(self) -> None:
        self.node.engine.node_manager.set_lock(self.node, lock=self.old)

    def needed(self, *, undoing: bool) -> bool:
        source, destination = _sides(self.old, self.new, undoing=undoing)
        if self.node.lock == destination:
            return False
        if self.node.lock != source:
            raise Conflict(STALE)
        return True


def is_live(target: BaseNode | ControlFlow) -> bool:
    """Whether a node or flow is part of the workflow, rather than deleted or never added."""
    return target.engine.object_manager.attempt_get_object_by_name(target.name) is target


def _sides[T](old: T, new: T, *, undoing: bool) -> tuple[T, T]:
    """Where a step starts and where it leads, in the direction it is being applied."""
    if undoing:
        return new, old
    return old, new


def _node_presence_needed(node: BaseNode, flow_name: str, *, present: bool) -> bool:
    if not present:
        return is_live(node)
    if is_live(node):
        return False
    object_manager = node.engine.object_manager
    if object_manager.has_object_with_name(node.name):
        raise Conflict(STALE)
    if object_manager.attempt_get_object_by_name(flow_name) is None:
        msg = f"'{flow_name}' no longer exists, so '{node.name}' cannot go back into it."
        raise Conflict(msg)
    return True


def _flow_presence_needed(flow: ControlFlow, *, present: bool) -> bool:
    if not present:
        return is_live(flow)
    if is_live(flow):
        return False
    if flow.engine.object_manager.has_object_with_name(flow.name):
        raise Conflict(STALE)
    return True


def _connection_presence_needed(connections: Connections, connection: Connection, *, present: bool) -> bool:
    if not present:
        return connections.contains(connection)
    if connections.contains(connection):
        return False
    for node in (connection.source_node, connection.target_node):
        if not is_live(node):
            msg = f"'{node.name}' no longer exists, so it cannot be reconnected."
            raise Conflict(msg)
    if connections.find_equivalent(connection) is not None:
        raise Conflict(STALE)
    return True


def _membership_needed(group: BaseNodeGroup, node: BaseNode, *, member: bool) -> bool:
    if not member:
        return node.parent_group is group or node.name in group.nodes
    if node.parent_group is group:
        return False
    if not is_live(group):
        msg = f"'{group.name}' no longer exists, so '{node.name}' cannot go back into it."
        raise Conflict(msg)
    if not is_live(node):
        msg = f"'{node.name}' no longer exists, so it cannot go back into '{group.name}'."
        raise Conflict(msg)
    if node.parent_group is not None:
        raise Conflict(STALE)
    return True
