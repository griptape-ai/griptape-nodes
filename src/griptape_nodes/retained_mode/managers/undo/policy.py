"""Which requests undo records, and which nodes a request can change.

Recording is opt-out. Every request a client sends is an edit unless it only reads state, runs
the workflow, or replaces the workflow outright. A new request type is therefore undoable without
registering anything. Recording is limited to nodes named by the fields below, the current context
node when `node_name=None`, and nodes in a flow named by a flow-wide request.
"""

from __future__ import annotations

from dataclasses import fields
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
from griptape_nodes.retained_mode.events.flow_events import AutoLayoutFlowRequest, DeleteFlowRequest
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

    READ = auto()

    UNRECORDED = auto()
    """Runs or saves the workflow. Nothing it changes is recorded, so undo never reverts a result."""

    RESETS_HISTORY = auto()
    """Replaces the workflow or the node types it is built from. Clears the history."""

    HISTORY = auto()


# Requests that only read state, named by convention. Skipping them keeps the editor's many reads
# from snapshotting the nodes they ask about.
_READ_PREFIXES = (
    "Can",
    "Check",
    "Compare",
    "Describe",
    "Get",
    "Has",
    "Inspect",
    "Is",
    "List",
    "Query",
    "Search",
    "Serialize",
    "Validate",
)

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

_FLOW_WIDE: frozenset[type[RequestPayload]] = frozenset({AutoLayoutFlowRequest, DeleteFlowRequest})

_NODE_NAME_FIELDS = (
    "node_name",
    "source_node_name",
    "target_node_name",
    "node_group_name",
    "parent_group_name",
    "object_name",
)
_NODE_NAMES_FIELDS = ("node_names", "node_names_to_add")
_NODE_NAME_KEYED_FIELDS = ("node_metadata_updates",)


def classify(request: RequestPayload) -> RequestRole:
    """The role a request plays for undo."""
    request_type = type(request)
    if request_type in _HISTORY:
        return RequestRole.HISTORY
    if request_type in _RESETS_HISTORY:
        return RequestRole.RESETS_HISTORY
    if request_type in _UNRECORDED:
        return RequestRole.UNRECORDED
    if request_type.__name__.startswith(_READ_PREFIXES):
        return RequestRole.READ
    return RequestRole.EDIT


def named_nodes(request: RequestPayload) -> list[str]:
    """Names of the nodes a request acts on, read from its fields.

    A name may refer to a node that does not exist yet, or to a flow; callers look each one up.
    """
    names: list[str] = []
    for request_field in fields(request):
        value = getattr(request, request_field.name)
        if request_field.name in _NODE_NAME_FIELDS and isinstance(value, str):
            names.append(value)
        elif (request_field.name in _NODE_NAMES_FIELDS and isinstance(value, list)) or (
            request_field.name in _NODE_NAME_KEYED_FIELDS and isinstance(value, dict)
        ):
            names.extend(name for name in value if isinstance(name, str))
        elif request_field.name == "nodes_to_duplicate" and isinstance(value, list):
            names.extend(entry[0] for entry in value if isinstance(entry, (list, tuple)) and entry)
    return names


def named_flow(request: RequestPayload) -> str | None:
    """The flow whose every node the request changes, if it is one of the requests that does."""
    if type(request) not in _FLOW_WIDE:
        return None
    flow_name = getattr(request, "flow_name", None)
    if isinstance(flow_name, str):
        return flow_name
    return None
