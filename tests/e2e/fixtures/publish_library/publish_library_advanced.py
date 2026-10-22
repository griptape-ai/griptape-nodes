"""Registers a workflow publisher that records what it was asked to publish, like a real publisher would read it.

Real publishers (Griptape Cloud, Deadline Cloud) name what they create after `workflow_name` and look
the workflow up with `WorkflowRegistry.get_workflow_by_name(workflow_name)`. This one does the same
lookup, writes what it found to the JSON file named by `PUBLISH_FIXTURE_RECORD_PATH`, and writes the
published file into the workspace, where the engine that asked for the publish looks for it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
from griptape_nodes.retained_mode.events.workflow_events import (
    PublishWorkflowRegisteredEventData,
    PublishWorkflowRequest,
    PublishWorkflowResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import Library, LibrarySchema
    from griptape_nodes.retained_mode.events.base_events import RequestPayload, ResultPayload

RECORD_PATH_ENV_VAR = "PUBLISH_FIXTURE_RECORD_PATH"


def _publish_workflow_request_handler(request: RequestPayload) -> ResultPayload:
    if not isinstance(request, PublishWorkflowRequest):
        msg = f"Expected PublishWorkflowRequest, got {type(request).__name__}"
        raise TypeError(msg)
    workflow_name = str(request.workflow_name)
    looked_up = WorkflowRegistry.get_workflow_by_name(workflow_name)
    record = {
        "workflow_name": workflow_name,
        "workflow_id": request.workflow_id,
        "looked_up_workflow_id": looked_up.workflow_id,
        "open_workflow_id": GriptapeNodes.ContextManager().get_current_workflow_id(),
    }
    Path(os.environ[RECORD_PATH_ENV_VAR]).write_text(json.dumps(record), encoding="utf-8")

    published_file = GriptapeNodes.ConfigManager().workspace_path / f"{request.published_workflow_file_name}.py"
    published_file.write_text("# Published by the Publish Library fixture.\n", encoding="utf-8")
    return PublishWorkflowResultSuccess(
        published_workflow_file_path=str(published_file),
        skip_published_workflow_registration=True,
        result_details=f"Published workflow '{workflow_name}'.",
    )


class PublishLibraryAdvanced(AdvancedNodeLibrary):
    def after_library_nodes_loaded(self, library_data: LibrarySchema, library: Library) -> None:  # noqa: ARG002 (hook signature)
        GriptapeNodes.LibraryManager().on_register_event_handler(
            request_type=PublishWorkflowRequest,
            handler=_publish_workflow_request_handler,
            library_data=library_data,
            event_data=PublishWorkflowRegisteredEventData(
                start_flow_node_type="PublishStartNode",
                start_flow_node_library_name=library_data.name,
                end_flow_node_type="PublishEndNode",
                end_flow_node_library_name=library_data.name,
            ),
        )
