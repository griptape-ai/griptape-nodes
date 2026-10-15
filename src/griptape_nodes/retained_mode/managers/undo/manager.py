from __future__ import annotations

import logging
import threading
from collections import deque
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from griptape_nodes.exe_types import journal
from griptape_nodes.exe_types.changes import is_live
from griptape_nodes.retained_mode.engine import EngineScoped
from griptape_nodes.retained_mode.events.base_events import AppEvent, ResultDetails
from griptape_nodes.retained_mode.events.undo_events import (
    ChangedConnection,
    ClearUndoHistoryRequest,
    ClearUndoHistoryResultSuccess,
    GetUndoHistoryRequest,
    GetUndoHistoryResultSuccess,
    RedoRequest,
    RedoResultFailure,
    RedoResultSuccess,
    UndoHistoryChanged,
    UndoRedoApplied,
    UndoRequest,
    UndoResultFailure,
    UndoResultSuccess,
)
from griptape_nodes.retained_mode.managers.undo.history import (
    HistoryEntry,
    Summary,
    describe,
    summarize,
)
from griptape_nodes.retained_mode.managers.undo.policy import RequestRole, classify
from griptape_nodes.retained_mode.request_handlers import handles

if TYPE_CHECKING:
    from griptape_nodes.exe_types.connections import Connection
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayload
    from griptape_nodes.retained_mode.managers.context_manager import ContextManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")

MAX_HISTORY = 100

# How many recent Undo and Redo groups to remember, so a client's reactions to them are not
# recorded as new edits even when the user presses Undo several times quickly.
MAX_ECHO_GROUPS = 16


class _NotRecording:
    """Marks a request whose writes, and those of everything it dispatches, are not recorded."""


_NOT_RECORDING = _NotRecording()


@dataclass
class Edit:
    """One user action, open for as long as more of its requests may arrive."""

    group: str
    transaction: journal.Transaction = field(default_factory=journal.Transaction)
    in_flight: int = 0
    entry: HistoryEntry | None = None
    # What the client called the action, if it named it.
    label: str | None = None


# Nested requests inherit the edit through the context variable.
_current_edit: ContextVar[Edit | _NotRecording | None] = ContextVar("undo_current_edit", default=None)


@dataclass
class DispatchScope:
    token: Token[Edit | _NotRecording | None]
    journal_token: Token[journal.Transaction | None]
    edit: Edit | None


class Direction(Enum):
    UNDO = auto()
    REDO = auto()


class UndoManager(EngineScoped):
    def __init__(self, event_manager: EventManager, *, engine: Engine | None = None) -> None:
        super().__init__(engine)
        self._undo: deque[HistoryEntry] = deque(maxlen=MAX_HISTORY)
        self._redo: list[HistoryEntry] = []
        # Edits that may still change: not yet committed, or committed and still on top of the stack.
        self._edits: dict[str, Edit] = {}
        self._echo_groups: deque[str] = deque(maxlen=MAX_ECHO_GROUPS)
        self._workflow: ContextManager.WorkflowContextState | None = None
        self._replaying = False
        self._lock = threading.RLock()
        event_manager.register_request_handlers(self)

    def begin_dispatch(self, request: RequestPayload) -> DispatchScope | None:
        """Let requests run even if recording fails."""
        try:
            return self._begin_dispatch(request)
        except Exception:
            logger.exception("Undo could not record %s. This change cannot be undone.", type(request).__name__)
            return None

    def end_dispatch(self, scope: DispatchScope | None) -> None:
        if scope is None:
            return
        journal.end(scope.journal_token)
        _current_edit.reset(scope.token)
        with self._lock:
            if scope.edit is not None:
                self._finish_request(scope.edit)
            # A client request can close the workflow, such as deleting the open one.
            if _current_edit.get() is None:
                self._forget_history_of_other_workflows()

    def clear_history(self) -> None:
        with self._lock:
            had_history = bool(self._undo or self._redo)
            self._undo.clear()
            self._redo.clear()
            self._edits = {group: edit for group, edit in self._edits.items() if edit.in_flight > 0}
            for edit in self._edits.values():
                edit.entry = None
        if had_history:
            self._notify()

    @handles(UndoRequest)
    def on_undo_request(self, request: UndoRequest) -> ResultPayload:
        with self._lock:
            self._forget_history_of_other_workflows()
            blocker = self._replay_blocker("undo")
            if blocker is not None:
                return UndoResultFailure(result_details=ResultDetails(message=blocker, level=logging.INFO))
            if not self._undo:
                details = "Attempted to undo. Failed because there is nothing to undo."
                return UndoResultFailure(result_details=ResultDetails(message=details, level=logging.INFO))
            entry = self._undo.pop()
            try:
                problems = self._apply(entry, Direction.UNDO, request.undo_group)
            except journal.Conflict as conflict:
                self._notify()
                details = f"Attempted to undo '{entry.label}'. Failed because {conflict}"
                return UndoResultFailure(result_details=ResultDetails(message=details, level=logging.WARNING))
            self._redo.append(entry)
            self._edits.clear()
        self._notify()
        return UndoResultSuccess(label=entry.label, result_details=_replay_details("Undid", entry, problems))

    @handles(RedoRequest)
    def on_redo_request(self, request: RedoRequest) -> ResultPayload:
        with self._lock:
            self._forget_history_of_other_workflows()
            blocker = self._replay_blocker("redo")
            if blocker is not None:
                return RedoResultFailure(result_details=ResultDetails(message=blocker, level=logging.INFO))
            if not self._redo:
                details = "Attempted to redo. Failed because there is nothing to redo."
                return RedoResultFailure(result_details=ResultDetails(message=details, level=logging.INFO))
            entry = self._redo.pop()
            try:
                problems = self._apply(entry, Direction.REDO, request.undo_group)
            except journal.Conflict as conflict:
                self._notify()
                details = f"Attempted to redo '{entry.label}'. Failed because {conflict}"
                return RedoResultFailure(result_details=ResultDetails(message=details, level=logging.WARNING))
            self._undo.append(entry)
            self._edits.clear()
        self._notify()
        return RedoResultSuccess(label=entry.label, result_details=_replay_details("Redid", entry, problems))

    @handles(GetUndoHistoryRequest)
    def on_get_undo_history_request(self, request: GetUndoHistoryRequest) -> ResultPayload:  # noqa: ARG002
        with self._lock:
            self._forget_history_of_other_workflows()
            undo_labels = [entry.label for entry in self._undo]
            redo_labels = [entry.label for entry in self._redo]
        return GetUndoHistoryResultSuccess(
            undo_labels=undo_labels,
            redo_labels=redo_labels,
            result_details=f"{len(undo_labels)} edits can be undone and {len(redo_labels)} redone.",
        )

    @handles(ClearUndoHistoryRequest)
    def on_clear_undo_history_request(self, request: ClearUndoHistoryRequest) -> ResultPayload:  # noqa: ARG002
        self.clear_history()
        return ClearUndoHistoryResultSuccess(result_details="Cleared the undo history.")

    def _begin_dispatch(self, request: RequestPayload) -> DispatchScope | None:  # noqa: PLR0911
        current = _current_edit.get()
        role = classify(request)

        if isinstance(current, Edit):
            # Nested requests write into the edit's transaction already, through the context.
            if role in (RequestRole.UNRECORDED, RequestRole.RESETS_HISTORY):
                return self._not_recording()
            return None
        if current is _NOT_RECORDING or role is RequestRole.HISTORY:
            return None
        if role is RequestRole.RESETS_HISTORY:
            self.clear_history()
            return self._not_recording()

        if request.undo_group is None:
            # Not part of a user action: the engine's own requests, a saved workflow replaying its
            # commands, or a library process reporting on a node it runs.
            return None
        if role is RequestRole.UNRECORDED or request.undo_group in self._echo_groups:
            return self._not_recording()

        with self._lock:
            self._forget_history_of_other_workflows()
            edit = self._edits.get(request.undo_group)
            if edit is None:
                edit = Edit(request.undo_group)
                self._edits[request.undo_group] = edit
            edit.in_flight += 1
            edit.transaction.accepting = True
            if request.undo_label:
                edit.label = request.undo_label
        return DispatchScope(token=_current_edit.set(edit), journal_token=journal.begin(edit.transaction), edit=edit)

    def _not_recording(self) -> DispatchScope:
        return DispatchScope(token=_current_edit.set(_NOT_RECORDING), journal_token=journal.begin(None), edit=None)

    def _finish_request(self, edit: Edit) -> None:
        edit.in_flight -= 1
        if edit.in_flight > 0:
            return
        edit.transaction.accepting = False
        try:
            self._commit(edit)
        except Exception:
            logger.exception("Undo could not record an edit. It cannot be undone.")
            self._edits.pop(edit.group, None)

    def _commit(self, edit: Edit) -> None:
        in_history = edit.entry is not None and any(entry is edit.entry for entry in self._undo)
        summary = summarize(edit.transaction)

        if not summary.changed:
            if in_history:
                self._undo = deque((other for other in self._undo if other is not edit.entry), maxlen=MAX_HISTORY)
                self._notify()
            self._edits.pop(edit.group, None)
            return

        label = edit.label or describe(summary)
        relabeled = edit.entry is not None and edit.entry.label != label
        if edit.entry is None:
            edit.entry = HistoryEntry(label=label, transaction=edit.transaction)
        edit.entry.label = label
        if not in_history:
            self._undo.append(edit.entry)
            self._redo.clear()
            # Only the edit on top of the stack may keep growing.
            self._edits = {group: other for group, other in self._edits.items() if other is edit or other.in_flight > 0}
        logger.debug("Recorded '%s' for %s: %d writes.", label, edit.group, len(edit.transaction.changes))
        if not in_history or relabeled:
            self._notify()

    def _apply(self, entry: HistoryEntry, direction: Direction, group: str | None) -> list[str]:
        """Move the workflow to the other side of an entry, and report what changed.

        Raises:
            journal.Conflict: Something outside the history changed the workflow so the entry cannot
                be applied. The workflow is left as it was.
        """
        summary = summarize(entry.transaction)
        # Read the touched part of the workflow on both sides, by name, so a rename reports the old
        # name as gone and every connection whose endpoint names changed as replaced.
        names_before = self._live_names(summary.touched)
        connections_before = self._connections_of(summary.touched)

        token = _current_edit.set(_NOT_RECORDING)
        self._replaying = True
        try:
            if direction is Direction.UNDO:
                problems = entry.transaction.undo()
            else:
                problems = entry.transaction.redo()
            self._invalidate_results(summary)
        finally:
            self._replaying = False
            _current_edit.reset(token)
        if group is not None:
            self._echo_groups.append(group)

        names_after = self._live_names(summary.touched)
        connections_after = self._connections_of(summary.touched)
        self.engine.event_manager.put_event(
            AppEvent(
                payload=UndoRedoApplied(
                    undo_group=group,
                    nodes_removed=sorted(names_before - names_after),
                    nodes_changed=sorted(names_after),
                    connections_removed=sorted(connections_before - connections_after, key=_connection_order),
                    connections_added=sorted(connections_after - connections_before, key=_connection_order),
                )
            )
        )
        return problems

    def _invalidate_results(self, summary: Summary) -> None:
        """Clear what a run left behind that the restored workflow no longer matches, as an edit does."""
        connections = self.engine.flow_manager.get_connections()
        for node, changes in summary.nodes.items():
            if is_live(node):
                for parameter_name in changes.values:
                    self.engine.node_manager.mark_value_changed(node, parameter_name)
        for node in summary.rerun_needed():
            if is_live(node):
                connections.unresolve_node_and_future_nodes(node)

    def _live_names(self, nodes: list[BaseNode]) -> set[str]:
        return {node.name for node in nodes if is_live(node)}

    def _connections_of(self, nodes: list[BaseNode]) -> set[ChangedConnection]:
        """Every live connection with a touched node at either end, by its endpoints' current names."""
        touched = {id(node) for node in nodes if is_live(node)}
        return {
            _changed_connection(connection)
            for connection in self.engine.flow_manager.get_connections().connections.values()
            if id(connection.source_node) in touched or id(connection.target_node) in touched
        }

    def _replay_blocker(self, verb: str) -> str | None:
        if self._replaying:
            return f"Attempted to {verb}. Failed because an undo or redo is already in progress."
        # An edit still running could be the one on top, half written. One that has written
        # nothing yet, such as a read, only records what happens after the replay.
        if any(edit.in_flight > 0 and edit.transaction.changes for edit in self._edits.values()):
            return f"Attempted to {verb}. Failed because the last change is still being applied."
        if self.engine.flow_manager.check_for_existing_running_flow():
            return f"Attempted to {verb}. Failed because the workflow is running."
        return None

    def _forget_history_of_other_workflows(self) -> None:
        # Compared by identity, since saving or moving a workflow renames it in place.
        workflow = self.engine.context_manager.get_current_workflow_state()
        if workflow is not self._workflow:
            self._workflow = workflow
            self.clear_history()

    def _notify(self) -> None:
        with self._lock:
            undo_label = self._undo[-1].label if self._undo else None
            redo_label = self._redo[-1].label if self._redo else None
        self.engine.event_manager.put_event(
            AppEvent(payload=UndoHistoryChanged(undo_label=undo_label, redo_label=redo_label))
        )


def _connection_order(connection: ChangedConnection) -> tuple[str, str, str, str]:
    return (
        connection.source_node_name,
        connection.source_parameter_name,
        connection.target_node_name,
        connection.target_parameter_name,
    )


def _changed_connection(connection: Connection) -> ChangedConnection:
    return ChangedConnection(
        source_node_name=connection.source_node.name,
        source_parameter_name=connection.source_parameter.name,
        target_node_name=connection.target_node.name,
        target_parameter_name=connection.target_parameter.name,
    )


def _replay_details(verb: str, entry: HistoryEntry, problems: list[str]) -> ResultDetails:
    if not problems:
        return ResultDetails(message=f"{verb} '{entry.label}'.", level=logging.DEBUG)
    listed = " ".join(problems)
    return ResultDetails(
        message=f"{verb} '{entry.label}', but some of it could not be restored. {listed}", level=logging.WARNING
    )
