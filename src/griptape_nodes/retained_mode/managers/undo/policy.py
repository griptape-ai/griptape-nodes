"""Which requests undo records.

Recording is opt-out. Every request a client sends records whatever it writes, unless it runs or
saves the workflow or replaces it outright. A request that only reads writes nothing, so it records
nothing, and a new request type is undoable without registering anything.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.events.context_events import SetWorkflowContextRequest
from griptape_nodes.retained_mode.events.execution_events import (
    CancelFlowRequest,
    ContinueExecutionStepRequest,
    ResolveNodeRequest,
    SingleExecutionStepRequest,
    SingleNodeStepRequest,
    StartFlowFromNodeRequest,
    StartFlowRequest,
    StartLocalSubflowRequest,
    UnresolveFlowRequest,
)
from griptape_nodes.retained_mode.events.library_events import (
    DownloadLibraryRequest,
    LoadLibrariesRequest,
    RegisterLibraryFromFileRequest,
    RegisterLibraryFromRequirementSpecifierRequest,
    RegisterSandboxNodeFromSourceRequest,
    ReloadAllLibrariesRequest,
    ReloadSandboxLibraryRequest,
    SwitchLibraryRefRequest,
    SyncLibrariesRequest,
    UnloadLibraryFromRegistryRequest,
    UpdateLibraryRequest,
)
from griptape_nodes.retained_mode.events.node_events import UnresolveNodeRequest
from griptape_nodes.retained_mode.events.object_events import ClearAllObjectStateRequest
from griptape_nodes.retained_mode.events.undo_events import (
    ClearUndoHistoryRequest,
    GetUndoHistoryRequest,
    RedoRequest,
    UndoRequest,
)
from griptape_nodes.retained_mode.events.workflow_events import (
    BranchWorkflowRequest,
    CreateWorkflowFromTemplateRequest,
    MergeWorkflowBranchRequest,
    PublishWorkflowRequest,
    ResetWorkflowBranchRequest,
    RunWorkflowFromRegistryRequest,
    RunWorkflowFromScratchRequest,
    RunWorkflowWithCurrentStateRequest,
    SaveWorkflowFileFromSerializedFlowRequest,
    SaveWorkflowRequest,
)

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.events.base_events import RequestPayload


class RequestRole(Enum):
    EDIT = auto()

    UNRECORDED = auto()
    """Runs or saves the workflow. Nothing it changes is recorded, so undo never reverts a result."""

    RESETS_HISTORY = auto()
    """Replaces the workflow or the node types it is built from. Clears the history."""

    HISTORY = auto()


_UNRECORDED: frozenset[type[RequestPayload]] = frozenset(
    {
        CancelFlowRequest,
        ContinueExecutionStepRequest,
        PublishWorkflowRequest,
        ResolveNodeRequest,
        RunWorkflowWithCurrentStateRequest,
        SaveWorkflowFileFromSerializedFlowRequest,
        SaveWorkflowRequest,
        # Opening a workflow is noticed by the context changing; it fails when one is already open.
        SetWorkflowContextRequest,
        SingleExecutionStepRequest,
        SingleNodeStepRequest,
        StartFlowFromNodeRequest,
        StartFlowRequest,
        StartLocalSubflowRequest,
        UnresolveFlowRequest,
        UnresolveNodeRequest,
    }
)

_RESETS_HISTORY: frozenset[type[RequestPayload]] = frozenset(
    {
        BranchWorkflowRequest,
        ClearAllObjectStateRequest,
        CreateWorkflowFromTemplateRequest,
        DownloadLibraryRequest,
        LoadLibrariesRequest,
        MergeWorkflowBranchRequest,
        RegisterLibraryFromFileRequest,
        RegisterLibraryFromRequirementSpecifierRequest,
        RegisterSandboxNodeFromSourceRequest,
        ReloadAllLibrariesRequest,
        ReloadSandboxLibraryRequest,
        ResetWorkflowBranchRequest,
        RunWorkflowFromRegistryRequest,
        RunWorkflowFromScratchRequest,
        SwitchLibraryRefRequest,
        SyncLibrariesRequest,
        UnloadLibraryFromRegistryRequest,
        UpdateLibraryRequest,
    }
)

_HISTORY: frozenset[type[RequestPayload]] = frozenset(
    {ClearUndoHistoryRequest, GetUndoHistoryRequest, RedoRequest, UndoRequest}
)


def classify(request: RequestPayload) -> RequestRole:
    """The role a request plays for undo."""
    request_type = type(request)
    if request_type in _HISTORY:
        return RequestRole.HISTORY
    if request_type in _RESETS_HISTORY:
        return RequestRole.RESETS_HISTORY
    if request_type in _UNRECORDED:
        return RequestRole.UNRECORDED
    return RequestRole.EDIT
