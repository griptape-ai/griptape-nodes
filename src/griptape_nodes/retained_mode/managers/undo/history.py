"""What a recorded edit changed, read from its changes, and a short label for it."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from griptape_nodes.exe_types.changes import (
    ConnectionAdded,
    ConnectionRemoved,
    FlowAdded,
    FlowRemoved,
    FlowReparented,
    GroupMemberAdded,
    GroupMemberRemoved,
    LockChanged,
    NodeAdded,
    NodeMoved,
    NodeRemoved,
    ObjectRenamed,
    ParameterRenamed,
    is_live,
)
from griptape_nodes.exe_types.elements.base import BaseNodeElement
from griptape_nodes.exe_types.journal import (
    MISSING,
    Aspect,
    InsertItem,
    JournaledDict,
    JournaledList,
    RemoveItem,
    SetAttribute,
    SetItem,
)
from griptape_nodes.exe_types.node_types import BaseNode

if TYPE_CHECKING:
    from collections.abc import Callable

    from griptape_nodes.exe_types.connections import Connection
    from griptape_nodes.exe_types.journal import Change, Transaction

# Library details in a node's metadata come from its library, and the editor writes them back with
# every move, so they do not label an edit.
LIBRARY_METADATA_KEYS = frozenset({"category", "library", "library_node_metadata", "node_type"})


# Records that change the workflow but not what an edit is labeled by.
_UNLABELED_RECORDS = (FlowAdded, FlowRemoved, FlowReparented, NodeMoved, ParameterRenamed)


@dataclass
class HistoryEntry:
    label: str
    transaction: Transaction


@dataclass
class NodeChanges:
    """How an edit changed a node that existed on both sides of it."""

    values: set[str] = field(default_factory=set)
    metadata: set[str] = field(default_factory=set)
    structure: bool = False
    # The group the node ended up in, MISSING when its group did not change.
    group: BaseNode | None = MISSING
    lock: bool | None = None


@dataclass
class Summary:
    """The net effect of a transaction. Nodes are the objects themselves, so names are read when needed."""

    changed: bool = False
    created: list[BaseNode] = field(default_factory=list)
    deleted: list[BaseNode] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    connections_added: list[Connection] = field(default_factory=list)
    connections_removed: list[Connection] = field(default_factory=list)
    nodes: dict[BaseNode, NodeChanges] = field(default_factory=lambda: defaultdict(NodeChanges))
    # Every node the transaction changed, including both ends of each connection it changed.
    touched: list[BaseNode] = field(default_factory=list)

    def rerun_needed(self) -> set[BaseNode]:
        """Nodes whose inputs changed, so their results no longer hold."""
        nodes = {node for node, changes in self.nodes.items() if changes.values or changes.structure}
        nodes.update(connection.target_node for connection in self.connections_added + self.connections_removed)
        return nodes


def summarize(transaction: Transaction) -> Summary:
    """The net effect of a transaction's changes."""
    return _Summarizer(transaction.changes).run()


class _Summarizer:
    def __init__(self, changes: list[Change]) -> None:
        self._changes = changes
        self._summary = Summary()
        self._touched: dict[int, BaseNode] = {}

    def run(self) -> Summary:
        self._read_structure()
        self._read_node_writes()
        summary = self._summary
        added_or_gone = {id(node) for node in summary.created + summary.deleted}
        summary.nodes = {node: changes for node, changes in summary.nodes.items() if id(node) not in added_or_gone}
        summary.touched = [node for node in self._touched.values() if self._in_workflow(node)]
        return summary

    def _read_structure(self) -> None:
        """Read the structural records, each kind netted over the edit."""
        for change in self._changes:
            for node in _nodes_of_record(change):
                self._touch(node)
        self._read_additions()
        self._read_node_records()
        summary = self._summary
        summary.changed = bool(
            summary.created
            or summary.deleted
            or summary.renamed
            or summary.connections_added
            or summary.connections_removed
            or summary.nodes
            or any(isinstance(change, _UNLABELED_RECORDS) for change in self._changes)
        )

    def _read_additions(self) -> None:
        summary = self._summary
        for chain in _chains(self._changes, NodeAdded | NodeRemoved, lambda change: change.node):
            if _appears(chain, NodeAdded):
                summary.created.append(chain[0].node)
            elif _disappears(chain, NodeAdded):
                summary.deleted.append(chain[0].node)
        for chain in _chains(self._changes, ConnectionAdded | ConnectionRemoved, lambda change: change.connection):
            if _appears(chain, ConnectionAdded):
                summary.connections_added.append(chain[0].connection)
            elif _disappears(chain, ConnectionAdded):
                summary.connections_removed.append(chain[0].connection)

    def _read_node_records(self) -> None:
        summary = self._summary
        for chain in _chains(self._changes, ObjectRenamed, lambda change: change.target):
            if chain[0].old_name != chain[-1].new_name:
                summary.renamed.append((chain[0].old_name, chain[-1].new_name))
        for chain in _chains(self._changes, GroupMemberAdded | GroupMemberRemoved, lambda change: change.node):
            before = chain[0].group if isinstance(chain[0], GroupMemberRemoved) else None
            after = chain[-1].group if isinstance(chain[-1], GroupMemberAdded) else None
            if before is not after:
                summary.nodes[chain[0].node].group = after
        for chain in _chains(self._changes, LockChanged, lambda change: change.node):
            if chain[0].old != chain[-1].new:
                summary.nodes[chain[0].node].lock = chain[-1].new

    def _read_node_writes(self) -> None:
        """Read the writes made inside nodes: their values, metadata, and elements."""
        for target, key, old, new in _net_writes(self._changes):
            node = _node_of(target)
            if node is None:
                # A flow's metadata, or an element no longer in a node.
                self._summary.changed = True
                continue
            if not self._in_workflow(node) or _same_value(target, key, old, new):
                continue
            self._summary.changed = True
            self._touch(node)
            self._read_write(node, target, key)
        for target in _changed_lists(self._changes):
            node = _node_of(target)
            if node is None:
                self._summary.changed = True
            elif self._in_workflow(node):
                self._summary.changed = True
                self._touch(node)
                self._summary.nodes[node].structure = True

    def _read_write(self, node: BaseNode, target: object, key: Any) -> None:
        aspect = getattr(target, "aspect", None)
        if aspect is Aspect.VALUES:
            self._summary.nodes[node].values.add(key)
        elif aspect is Aspect.METADATA:
            metadata_key = key if target.root_key is MISSING else target.root_key  # type: ignore[attr-defined]
            if metadata_key not in LIBRARY_METADATA_KEYS:
                self._summary.nodes[node].metadata.add(metadata_key)
        elif isinstance(target, BaseNodeElement) or aspect in (
            Aspect.CHILDREN,
            Aspect.GROUP_PROXIES,
            Aspect.ADDED_PARAMETERS,
        ):
            self._summary.nodes[node].structure = True

    def _touch(self, node: BaseNode) -> None:
        self._touched.setdefault(id(node), node)

    def _in_workflow(self, node: BaseNode) -> bool:
        """Whether a node is in the workflow on one side of the edit, rather than one no one could see."""
        if is_live(node):
            return True
        return any(node is other for other in self._summary.created + self._summary.deleted)


def describe(summary: Summary) -> str:  # noqa: C901, PLR0911
    """A short label for an edit, read from what it changed rather than which requests made it.

    The most telling change wins. Connecting a parameter also sets its value, for example, so a
    new connection outranks the value change that came with it.
    """
    nodes = summary.nodes
    if summary.created and summary.deleted:
        return f"Edit {_count(len(summary.created) + len(summary.deleted), 'node')}"
    if summary.created:
        return f"Add {_name_list([node.name for node in summary.created])}"
    if summary.deleted:
        return f"Delete {_name_list([node.name for node in summary.deleted])}"
    if summary.renamed:
        if len(summary.renamed) == 1:
            old, new = summary.renamed[0]
            return f"Rename '{old}' to '{new}'"
        return f"Rename {_count(len(summary.renamed), 'node')}"
    regrouped = [node for node, changes in nodes.items() if changes.group is not MISSING]
    if regrouped:
        verb = "Group" if any(nodes[node].group is not None for node in regrouped) else "Ungroup"
        return f"{verb} {_name_list([node.name for node in regrouped])}"
    if summary.connections_added or summary.connections_removed:
        return _describe_connections(summary)
    valued = [(node, changes.values) for node, changes in nodes.items() if changes.values]
    if len(valued) == 1 and len(valued[0][1]) == 1:
        node, values = valued[0]
        return f"Change '{next(iter(values))}' on '{node.name}'"
    restructured = sorted(node.name for node, changes in nodes.items() if changes.structure)
    if restructured and not valued:
        return f"Edit parameters on {_name_list(restructured)}"
    if not valued:
        label = _describe_layout_or_lock(nodes)
        if label is not None:
            return label
    names = sorted(node.name for node in summary.touched)
    if names:
        return f"Edit {_name_list(names)}"
    return "Edit workflow"


def _describe_connections(summary: Summary) -> str:
    added, removed = summary.connections_added, summary.connections_removed
    if len(added) == 1 and not removed:
        return f"Connect '{added[0].source_node.name}' to '{added[0].target_node.name}'"
    if len(removed) == 1 and not added:
        return f"Disconnect '{removed[0].source_node.name}' from '{removed[0].target_node.name}'"
    return "Change connections"


def _describe_layout_or_lock(nodes: dict[BaseNode, NodeChanges]) -> str | None:
    keys = set().union(*(changes.metadata for changes in nodes.values()))
    locked = [node for node, changes in nodes.items() if changes.lock is not None]
    if locked and not keys:
        verb = "Lock" if nodes[locked[0]].lock else "Unlock"
        return f"{verb} {_name_list([node.name for node in locked])}"
    moved = sorted(node.name for node, changes in nodes.items() if changes.metadata)
    if keys == {"position"}:
        return f"Move {_name_list(moved)}"
    if keys and keys <= {"position", "size"}:
        return f"Resize {_name_list(moved)}"
    return None


def _chains(changes: list[Change], kinds: Any, key: Callable[[Any], object]) -> list[list[Any]]:
    """The records of the given kinds, grouped by the object each is about, in order."""
    chains: dict[int, list[Any]] = {}
    for change in changes:
        if isinstance(change, kinds):
            chains.setdefault(id(key(change)), []).append(change)
    return list(chains.values())


def _appears(chain: list[Change], present: type) -> bool:
    """Whether a chain of opposite records adds something that was not there before the edit."""
    return isinstance(chain[0], present) and isinstance(chain[-1], present)


def _disappears(chain: list[Change], present: type) -> bool:
    """Whether a chain of opposite records removes something that was there before the edit."""
    return not isinstance(chain[0], present) and not isinstance(chain[-1], present)


def _nodes_of_record(change: Change) -> list[BaseNode]:
    if isinstance(change, NodeAdded | NodeRemoved | NodeMoved | LockChanged | ParameterRenamed):
        return [change.node]
    if isinstance(change, GroupMemberAdded | GroupMemberRemoved):
        return [change.node, change.group]
    if isinstance(change, ConnectionAdded | ConnectionRemoved):
        return [change.connection.source_node, change.connection.target_node]
    if isinstance(change, ObjectRenamed) and isinstance(change.target, BaseNode):
        return [change.target]
    return []


def _node_of(value: Any) -> BaseNode | None:
    """The node an element or journaled container belongs to, if any."""
    if isinstance(value, BaseNode):
        return value
    if isinstance(value, BaseNodeElement):
        return value._node_context
    if isinstance(value, JournaledDict | JournaledList):
        return _node_of(value.owner)
    return None


def _net_writes(changes: list[Change]) -> list[tuple[object, Any, Any, Any]]:
    """Each key and attribute written, with its value before the edit and after it."""
    first: dict[tuple[int, bool, Any], Any] = {}
    last: dict[tuple[int, bool, Any], tuple[object, Any, Any]] = {}
    for change in changes:
        if isinstance(change, SetItem):
            place = (id(change.target), True, change.key)
            key = change.key
        elif isinstance(change, SetAttribute):
            place = (id(change.target), False, change.name)
            key = change.name
        else:
            continue
        first.setdefault(place, change.old)
        last[place] = (change.target, key, change.new)
    return [
        (target, key, first[place], new) for place, (target, key, new) in last.items() if not _same(first[place], new)
    ]


def _changed_lists(changes: list[Change]) -> list[list]:
    """Lists whose items or order differ after the edit from before it."""
    lists: dict[int, list] = {}
    history: dict[tuple[int, int], list[InsertItem | RemoveItem]] = defaultdict(list)
    for change in changes:
        if isinstance(change, InsertItem | RemoveItem):
            lists[id(change.target)] = change.target
            history[id(change.target), id(change.item)].append(change)
    changed: set[int] = set()
    for (list_id, _), item_history in history.items():
        first, last = item_history[0], item_history[-1]
        was_there, is_there = isinstance(first, RemoveItem), isinstance(last, InsertItem)
        # Present on one side only, or taken out and put back somewhere else.
        if was_there != is_there or (was_there and first.index != last.index):
            changed.add(list_id)
    return [lists[list_id] for list_id in changed]


def _same_value(target: object, name: Any, old: Any, new: Any) -> bool:
    """Whether an unset parameter value and its default stand for the same thing."""
    owner = getattr(target, "owner", None)
    if getattr(target, "aspect", None) is not Aspect.VALUES or not isinstance(owner, BaseNode):
        return False
    if old is not MISSING and new is not MISSING:
        return False
    parameter = owner.get_parameter_by_name(name)
    if parameter is None:
        return False
    value = new if old is MISSING else old
    return _same(value, parameter.default_value)


def _name_list(names: list[str]) -> str:
    if len(names) == 1:
        return f"'{names[0]}'"
    return _count(len(names), "node")


def _count(count: int, noun: str) -> str:
    if count == 1:
        return f"1 {noun}"
    return f"{count} {noun}s"


def _same(left: Any, right: Any) -> bool:
    if left is right:
        return True
    try:
        return bool(left == right)
    except Exception:
        return False
