"""The flow hierarchy and connections of one open workflow.

`WorkflowFlows` is the state a `WorkflowRuntime` keeps as `flows`. `FlowManager` is the behavior that
creates, connects, serializes, and runs flows against it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.exe_types.connections import Connections

if TYPE_CHECKING:
    from griptape_nodes.exe_types.flow import ControlFlow


class WorkflowFlows:
    """The flows of one open workflow, how they nest, and how their nodes connect."""

    def __init__(self) -> None:
        # flow name -> its parent flow's name, None for the top-level flow (the canvas).
        self.name_to_parent_name: dict[str, str | None] = {}
        # The flows made by importing a referenced workflow, and that workflow's name.
        self.flow_to_referenced_workflow_name: dict[ControlFlow, str] = {}
        self.connections = Connections()
