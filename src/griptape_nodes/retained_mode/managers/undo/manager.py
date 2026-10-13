from __future__ import annotations

import logging
import threading
from collections import deque
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.retained_mode.engine import EngineScoped
from griptape_nodes.retained_mode.events.base_events import AppEvent, ResultDetails
from griptape_nodes.retained_mode.events.undo_events import (
    ClearUndoHistoryRequest,
    ClearUndoHistoryResultSuccess,
    GetUndoHistoryRequest,
    GetUndoHistoryResultSuccess,
    RedoRequest,
    RedoResultFailure,
    RedoResultSuccess,
    UndoHistoryChanged,
    UndoRequest,
    UndoResultFailure,
    UndoResultSuccess,
)
from griptape_nodes.retained_mode.managers.undo.history import describe_changes
from griptape_nodes.retained_mode.managers.undo.policy import RequestRole, classify
from griptape_nodes.retained_mode.managers.undo.recording import Edit
from griptape_nodes.retained_mode.managers.undo.replay import Direction, replay
from griptape_nodes.retained_mode.request_handlers import handles

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.engine import Engine
    from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayload
    from griptape_nodes.retained_mode.managers.context_manager import ContextManager
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.undo.history import HistoryEntry

logger = logging.getLogger("griptape_nodes")

MAX_HISTORY = 100

# How many recent Undo and Redo groups to remember, so a client's reactions to them are not
# recorded as new edits even when the user presses Undo several times quickly.
MAX_ECHO_GROUPS = 16


class _NotRecording:
    """Marks a request whose changes, and those of everything it dispatches, are not recorded."""


_NOT_RECORDING = _NotRecording()


@dataclass(frozen=True)
class _Replaying:
    """Marks the requests an undo or redo issues. Each is tagged with the Undo or Redo request's group.

    The tag lets a client tell a replayed result from one it should react to: a replay already
    describes the state to show, so answering it with requests of its own would only fight it.
    """

    group: str | None


# Nested requests inherit the edit through the context variable.
_current_edit: ContextVar[Edit | _NotRecording | _Replaying | None] = ContextVar("undo_current_edit", default=None)


@dataclass
class DispatchScope:
    token: Token[Edit | _NotRecording | _Replaying | None]
    edit: Edit | None


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
        _current_edit.reset(scope.token)
        with self._lock:
            if scope.edit is not None:
                self._finish_request(scope.edit)
            # A client request can close the workflow, such as deleting the open one.
            if _current_edit.get() is None:
                self._forget_history_of_other_workflows()

    def note_object_created(self, obj: object) -> None:
        current = _current_edit.get()
        if not isinstance(current, Edit) or current.in_flight == 0 or not isinstance(obj, BaseNode):
            return
        current.note_created(obj)

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
            problems = self._replay(entry, Direction.UNDO, request.undo_group)
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
            problems = self._replay(entry, Direction.REDO, request.undo_group)
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

    def _begin_dispatch(self, request: RequestPayload) -> DispatchScope | None:
        current = _current_edit.get()
        role = classify(request)

        if isinstance(current, Edit):
            return self._begin_nested(current, request, role)
        if isinstance(current, _Replaying):
            request.undo_group = request.undo_group or current.group
            return None
        if current is _NOT_RECORDING or role in (RequestRole.READ, RequestRole.HISTORY):
            return None
        if role is RequestRole.RESETS_HISTORY:
            self.clear_history()
            return DispatchScope(token=_current_edit.set(_NOT_RECORDING), edit=None)

        if request.undo_group is None:
            # Not part of a user action: the engine's own requests, a saved workflow replaying its
            # commands, or a library process reporting on a node it runs.
            return None
        return self._begin_client_request(request, role, request.undo_group)

    def _begin_client_request(self, request: RequestPayload, role: RequestRole, group: str) -> DispatchScope:
        if role is RequestRole.UNRECORDED or group in self._echo_groups:
            return DispatchScope(token=_current_edit.set(_NOT_RECORDING), edit=None)

        with self._lock:
            self._forget_history_of_other_workflows()
            edit = self._edits.get(group)
            if edit is None:
                edit = Edit(self.engine, group)
                self._edits[group] = edit
            # Imaged before the edit counts the request, so a capture that raises leaves nothing behind.
            edit.capture_named(self.engine, request)
            edit.in_flight += 1
        return DispatchScope(token=_current_edit.set(edit), edit=edit)

    def _begin_nested(self, edit: Edit, request: RequestPayload, role: RequestRole) -> DispatchScope | None:
        if role in (RequestRole.UNRECORDED, RequestRole.RESETS_HISTORY):
            return DispatchScope(token=_current_edit.set(_NOT_RECORDING), edit=None)
        # A task a handler left running can dispatch after the edit is done. It is no longer
        # part of what the user did.
        if role is RequestRole.READ or edit.in_flight == 0:
            return None
        with self._lock:
            edit.capture_named(self.engine, request)
        return None

    def _finish_request(self, edit: Edit) -> None:
        edit.in_flight -= 1
        if edit.in_flight > 0:
            return
        try:
            self._commit(edit)
        except Exception:
            logger.exception("Undo could not record an edit. It cannot be undone.")
            self._edits.pop(edit.group, None)

    def _commit(self, edit: Edit) -> None:
        previous_label = self._undo[-1].label if self._undo else None
        in_history = edit.entry is not None and any(entry is edit.entry for entry in self._undo)
        entry = edit.finish(self.engine)

        if entry.is_empty():
            if in_history:
                self._undo = deque((other for other in self._undo if other is not entry), maxlen=MAX_HISTORY)
                self._notify()
            self._edits.pop(edit.group, None)
            return
        if not in_history:
            self._undo.append(entry)
            self._redo.clear()
            # Only the edit on top of the stack may keep growing.
            self._edits = {group: other for group, other in self._edits.items() if other is edit or other.in_flight > 0}
        logger.debug("Recorded '%s' for %s: %s", entry.label, edit.group, describe_changes(entry))
        if not in_history or entry.label != previous_label:
            self._notify()

    def _replay(self, entry: HistoryEntry, direction: Direction, group: str | None) -> list[str]:
        if group is not None:
            self._echo_groups.append(group)
        token = _current_edit.set(_Replaying(group))
        self._replaying = True
        try:
            return replay(self.engine, entry, direction)
        except Exception as err:
            logger.exception("Undo could not finish restoring '%s'.", entry.label)
            return [f"Stopped partway because of an unexpected error: {err}"]
        finally:
            self._replaying = False
            _current_edit.reset(token)

    def _replay_blocker(self, verb: str) -> str | None:
        if self._replaying:
            return f"Attempted to {verb}. Failed because an undo or redo is already in progress."
        # An edit imaged the connections when it began, even if it has not named a node yet. A replay
        # in the meantime would land in its entry and clear redo, so every edit still running blocks it.
        if any(edit.in_flight > 0 for edit in self._edits.values()):
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


def _replay_details(verb: str, entry: HistoryEntry, problems: list[str]) -> ResultDetails:
    if not problems:
        return ResultDetails(message=f"{verb} '{entry.label}'.", level=logging.DEBUG)
    listed = " ".join(problems)
    return ResultDetails(
        message=f"{verb} '{entry.label}', but some of it could not be restored. {listed}", level=logging.WARNING
    )
