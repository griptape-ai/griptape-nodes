from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.undo.snapshot import ConnectionKey, NodeImage


@dataclass
class NodeChange:
    """None on either side means the node did not exist there."""

    before: NodeImage | None
    after: NodeImage | None


@dataclass
class HistoryEntry:
    """Changes follow first-touch order; connection endpoints use names from their side of the edit."""

    label: str = ""
    changes: list[NodeChange] = field(default_factory=list)
    connections_removed: frozenset[ConnectionKey] = frozenset()
    connections_added: frozenset[ConnectionKey] = frozenset()

    def is_empty(self) -> bool:
        return not self.changes and not self.connections_removed and not self.connections_added


def describe(entry: HistoryEntry) -> str:
    """A short label for an edit, read from what it changed rather than which requests made it."""
    created = [change.after for change in entry.changes if change.before is None and change.after is not None]
    deleted = [change.before for change in entry.changes if change.after is None and change.before is not None]
    modified = [
        (change.before, change.after)
        for change in entry.changes
        if change.before is not None and change.after is not None
    ]

    if created and deleted:
        if {image.name for image in created} == {image.name for image in deleted}:
            return f"Reset {_name_list([image.name for image in created])}"
        return f"Edit {_count(len(created) + len(deleted) + len(modified), 'node')}"
    if created:
        return f"Add {_name_list([image.name for image in created])}"
    if deleted:
        return f"Delete {_name_list([image.name for image in deleted])}"
    if not modified:
        return _describe_connections(entry)
    return _describe_modified(modified, entry)


type _Modified = list[tuple[NodeImage, NodeImage]]


def describe_changes(entry: HistoryEntry) -> str:
    """What an entry changed, node by node, for the log."""
    parts = []
    for change in entry.changes:
        before, after = change.before, change.after
        if before is None and after is not None:
            parts.append(f"added {after.name}")
        elif after is None and before is not None:
            parts.append(f"deleted {before.name}")
        elif before is not None and after is not None:
            changed = sorted(before.changed_metadata_keys(after)) + sorted(before.changed_values(after))
            if before.structure != after.structure:
                changed.append("<parameters>")
            parts.append(f"{after.name} [{', '.join(changed)}]")
    parts.extend(f"connected {key.source_node}.{key.source_parameter}" for key in entry.connections_added)
    parts.extend(f"disconnected {key.source_node}.{key.source_parameter}" for key in entry.connections_removed)
    return "; ".join(parts)


def _describe_modified(modified: _Modified, entry: HistoryEntry) -> str:
    """Label an edit that changed nodes without adding or removing any.

    The most telling change wins. Connecting a parameter also sets its value, for example, so a new
    connection outranks the value change that came with it.
    """
    for describe_change in (
        _describe_renames,
        _describe_grouping,
        _describe_rewiring,
        _describe_parameter_set,
        _describe_values,
        _describe_structure,
        _describe_locks,
        _describe_layout,
    ):
        label = describe_change(modified, entry)
        if label is not None:
            return label
    return f"Edit {_name_list([after.name for _, after in modified])}"


def _describe_renames(modified: _Modified, entry: HistoryEntry) -> str | None:  # noqa: ARG001
    renamed = [(before, after) for before, after in modified if before.name != after.name]
    if not renamed:
        return None
    if len(renamed) == 1:
        before, after = renamed[0]
        return f"Rename '{before.name}' to '{after.name}'"
    return f"Rename {_count(len(renamed), 'node')}"


def _describe_grouping(modified: _Modified, entry: HistoryEntry) -> str | None:  # noqa: ARG001
    moved = [(before, after) for before, after in modified if before.parent_group != after.parent_group]
    if not moved:
        return None
    grouped = [after.name for _, after in moved if after.parent_group is not None]
    if grouped:
        return f"Group {_name_list(grouped)}"
    return f"Ungroup {_name_list([after.name for _, after in moved])}"


def _describe_rewiring(modified: _Modified, entry: HistoryEntry) -> str | None:  # noqa: ARG001
    if entry.connections_added or entry.connections_removed:
        return _describe_connections(entry)
    return None


def _describe_parameter_set(modified: _Modified, entry: HistoryEntry) -> str | None:  # noqa: ARG001
    for before, after in modified:
        added = [name for name in after.parameters if name not in before.parameters]
        removed = [name for name in before.parameters if name not in after.parameters]
        if len(added) == 1 and not removed:
            return f"Add '{added[0]}' to '{after.name}'"
        if len(removed) == 1 and not added:
            return f"Remove '{removed[0]}' from '{after.name}'"
        if added or removed:
            return f"Edit parameters on '{after.name}'"
    return None


def _describe_values(modified: _Modified, entry: HistoryEntry) -> str | None:  # noqa: ARG001
    for before, after in modified:
        parameters = before.changed_values(after)
        if len(parameters) == 1:
            return f"Change '{next(iter(parameters))}' on '{after.name}'"
        if parameters:
            return f"Change {_count(len(parameters), 'value')} on '{after.name}'"
    return None


def _describe_structure(modified: _Modified, entry: HistoryEntry) -> str | None:  # noqa: ARG001
    changed = [after.name for before, after in modified if before.structure != after.structure]
    if changed:
        return f"Edit parameters on {_name_list(changed)}"
    return None


def _describe_locks(modified: _Modified, entry: HistoryEntry) -> str | None:  # noqa: ARG001
    changed = [after for before, after in modified if before.lock != after.lock]
    if not changed or any(before.changed_metadata_keys(after) for before, after in modified):
        return None
    verb = "Lock" if changed[0].lock else "Unlock"
    return f"{verb} {_name_list([after.name for after in changed])}"


def _describe_layout(modified: _Modified, entry: HistoryEntry) -> str | None:  # noqa: ARG001
    changed_keys: set[str] = set()
    for before, after in modified:
        changed_keys |= before.changed_metadata_keys(after)
    names = [after.name for _, after in modified]
    if changed_keys == {"position"}:
        return f"Move {_name_list(names)}"
    if changed_keys and changed_keys <= {"position", "size"}:
        return f"Resize {_name_list(names)}"
    return None


def _describe_connections(entry: HistoryEntry) -> str:
    added = sorted(entry.connections_added)
    removed = sorted(entry.connections_removed)
    if len(added) == 1 and not removed:
        key = added[0]
        return f"Connect '{key.source_node}' to '{key.target_node}'"
    if len(removed) == 1 and not added:
        key = removed[0]
        return f"Disconnect '{key.source_node}' from '{key.target_node}'"
    if added and not removed:
        return f"Add {_count(len(added), 'connection')}"
    if removed and not added:
        return f"Remove {_count(len(removed), 'connection')}"
    return "Change connections"


def _name_list(names: list[str]) -> str:
    if len(names) == 1:
        return f"'{names[0]}'"
    return _count(len(names), "node")


def _count(count: int, noun: str) -> str:
    if count == 1:
        return f"1 {noun}"
    return f"{count} {noun}s"
