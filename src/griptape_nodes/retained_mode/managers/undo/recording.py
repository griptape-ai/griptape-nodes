from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.exe_types.flow import ControlFlow
from griptape_nodes.exe_types.node_groups.base_node_group import BaseNodeGroup
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.managers.undo.history import HistoryEntry, NodeChange, describe
from griptape_nodes.retained_mode.managers.undo.policy import named_flow, named_nodes
from griptape_nodes.retained_mode.managers.undo.snapshot import ConnectionKey, NodeImage, capture_node, is_live

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import RequestPayload

# A connection by the identities of its endpoint nodes, so renames and replacements do not alias.
type _ConnectionIdentity = tuple[int, str, int, str]


class _Unrecordable:
    """Marks a node that could not be imaged. Its changes are left out of the edit."""


_UNRECORDABLE = _Unrecordable()


class Edit:
    """The recording of one user action, open for as long as more of its requests may arrive."""

    def __init__(self, engine: Engine, group: str) -> None:
        self.group = group
        self.in_flight = 0
        self.entry: HistoryEntry | None = None
        # Object identities distinguish renames from replacements under the same name.
        # Strong references keep the ids used as keys below from being reused while the edit is open.
        self._nodes: dict[int, BaseNode] = {}
        self._before: dict[int, NodeImage | _Unrecordable | None] = {}
        self._after: dict[int, NodeImage | _Unrecordable | None] = {}
        self._dirty: dict[int, BaseNode] = {}
        self._endpoints: dict[int, BaseNode] = {}
        self._before_connections = self._connection_table(engine)

    @property
    def touched(self) -> bool:
        return bool(self._nodes)

    def capture_named(self, engine: Engine, request: RequestPayload) -> None:
        for node in _nodes_for(engine, request):
            self.capture(engine, node)
            if isinstance(node, BaseNodeGroup):
                # A group releases its members itself when it is deleted, with no request naming them.
                for member in list(node.nodes.values()):
                    self.capture(engine, member)

    def capture(self, engine: Engine, node: BaseNode) -> None:
        """Image a node before the edit changes it. Later calls only mark the node touched again."""
        node_id = id(node)
        self._dirty[node_id] = node
        if node_id in self._before:
            return
        self._nodes[node_id] = node
        image = capture_node(engine, node)
        self._before[node_id] = _UNRECORDABLE if image is None else image

    def note_created(self, node: BaseNode) -> None:
        node_id = id(node)
        self._dirty[node_id] = node
        if node_id in self._before:
            return
        self._nodes[node_id] = node
        self._before[node_id] = None

    def finish(self, engine: Engine) -> HistoryEntry:
        for node_id, node in self._dirty.items():
            if not is_live(engine, node):
                self._after[node_id] = None
                continue
            image = capture_node(engine, node)
            self._after[node_id] = _UNRECORDABLE if image is None else image
        self._dirty.clear()

        after_connections = self._connection_table(engine)
        entry = self.entry if self.entry is not None else HistoryEntry()
        entry.changes = self._changes()
        entry.connections_removed = frozenset(
            key for identity, key in self._before_connections.items() if identity not in after_connections
        )
        entry.connections_added = frozenset(
            key for identity, key in after_connections.items() if identity not in self._before_connections
        )
        entry.label = describe(entry)
        self.entry = entry
        return entry

    def _changes(self) -> list[NodeChange]:
        changes = []
        for node_id in self._nodes:
            before = self._before[node_id]
            after = self._after.get(node_id, _UNRECORDABLE)
            if isinstance(before, _Unrecordable) or isinstance(after, _Unrecordable):
                continue
            if before is None and after is None:
                continue
            if before is not None and after is not None and before.same_state(after):
                continue
            changes.append(NodeChange(before=before, after=after))
        return changes

    def _connection_table(self, engine: Engine) -> dict[_ConnectionIdentity, ConnectionKey]:
        # Connections are a small flat table, so the edit copies the whole table when it starts and compares
        # it with the table at the end. Copying only the connections of each node as the edit first touches it
        # would miss rewiring the engine does on its own before a request names that node.
        table: dict[_ConnectionIdentity, ConnectionKey] = {}
        for connection in list(engine.flow_manager.get_connections().connections.values()):
            source, target = connection.source_node, connection.target_node
            self._endpoints[id(source)] = source
            self._endpoints[id(target)] = target
            identity = (id(source), connection.source_parameter.name, id(target), connection.target_parameter.name)
            table[identity] = ConnectionKey(
                source_node=source.name,
                source_parameter=connection.source_parameter.name,
                target_node=target.name,
                target_parameter=connection.target_parameter.name,
            )
        return table


def _nodes_for(engine: Engine, request: RequestPayload) -> list[BaseNode]:
    nodes: list[BaseNode] = []
    for name in named_nodes(request):
        node = engine.object_manager.attempt_get_object_by_name_as_type(name, BaseNode)
        if node is not None:
            nodes.append(node)
    # Match the current-node fallback in node handlers.
    if getattr(request, "node_name", "") is None and engine.context_manager.has_current_node():
        nodes.append(engine.context_manager.get_current_node())

    flow_name = named_flow(request)
    if flow_name is not None:
        flow = engine.object_manager.attempt_get_object_by_name_as_type(flow_name, ControlFlow)
        if flow is not None:
            nodes.extend(flow.nodes.values())
    return nodes
