"""Requests and notifications for undoing and redoing edits to the current workflow."""

from dataclasses import dataclass, field

from griptape_nodes.retained_mode.events.base_events import (
    AppPayload,
    RequestPayload,
    ResultPayloadFailure,
    ResultPayloadSuccess,
    WorkflowAlteredMixin,
    WorkflowNotAlteredMixin,
)
from griptape_nodes.retained_mode.events.payload_registry import PayloadRegistry


@dataclass
@PayloadRegistry.register
class UndoRequest(RequestPayload):
    """Revert the most recent edit to the current workflow.

    Use when: The user presses Undo. Requests sent afterwards with the same `undo_group` are
    treated as the client's reaction to the undo and are not recorded as a new edit.

    Results: UndoResultSuccess (with the label of the edit undone) | UndoResultFailure (nothing to
    undo, a workflow is running, or an edit is still being applied)
    """


@dataclass
@PayloadRegistry.register
class UndoResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """The edit was reverted.

    Args:
        label: What the edit did, such as "Move 3 nodes"
    """

    label: str


@dataclass
@PayloadRegistry.register
class UndoResultFailure(ResultPayloadFailure):
    """Nothing was undone."""


@dataclass
@PayloadRegistry.register
class RedoRequest(RequestPayload):
    """Re-apply the most recently undone edit.

    Use when: The user presses Redo. Requests sent afterwards with the same `undo_group` are treated
    as the client's reaction to the redo and are not recorded as a new edit.

    Results: RedoResultSuccess (with the label of the edit redone) | RedoResultFailure (nothing to
    redo, a workflow is running, or an edit is still being applied)
    """


@dataclass
@PayloadRegistry.register
class RedoResultSuccess(WorkflowAlteredMixin, ResultPayloadSuccess):
    """The edit was re-applied.

    Args:
        label: What the edit did, such as "Move 3 nodes"
    """

    label: str


@dataclass
@PayloadRegistry.register
class RedoResultFailure(ResultPayloadFailure):
    """Nothing was redone."""


@dataclass
@PayloadRegistry.register
class GetUndoHistoryRequest(RequestPayload):
    """List the edits that can be undone and redone.

    Results: GetUndoHistoryResultSuccess
    """


@dataclass
@PayloadRegistry.register
class GetUndoHistoryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """The edits that can be undone and redone.

    Args:
        undo_labels: Edits Undo would revert, most recent last
        redo_labels: Edits Redo would re-apply, next one last
    """

    undo_labels: list[str] = field(default_factory=list)
    redo_labels: list[str] = field(default_factory=list)


@dataclass
@PayloadRegistry.register
class GetUndoHistoryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """The history could not be read."""


@dataclass
@PayloadRegistry.register
class ClearUndoHistoryRequest(RequestPayload):
    """Forget every edit that could be undone or redone.

    Results: ClearUndoHistoryResultSuccess
    """


@dataclass
@PayloadRegistry.register
class ClearUndoHistoryResultSuccess(WorkflowNotAlteredMixin, ResultPayloadSuccess):
    """The history is empty."""


@dataclass
@PayloadRegistry.register
class ClearUndoHistoryResultFailure(WorkflowNotAlteredMixin, ResultPayloadFailure):
    """The history could not be cleared."""


@dataclass
@PayloadRegistry.register
class UndoHistoryChanged(AppPayload):
    """The edits available to Undo and Redo changed.

    Sent when an edit is recorded, undone, or redone, and when the history is cleared, so an editor
    can enable its Undo and Redo commands and name what they will do.

    Args:
        undo_label: What Undo would revert, or None when there is nothing to undo
        redo_label: What Redo would re-apply, or None when there is nothing to redo
    """

    undo_label: str | None = None
    redo_label: str | None = None
