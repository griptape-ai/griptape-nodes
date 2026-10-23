"""The flow hierarchy, connections, and run state of one open workflow.

`WorkflowFlows` is the state a `WorkflowRuntime` keeps as `flows`. `FlowManager` is the behavior that
creates, connects, serializes, and runs flows against it.
"""

from __future__ import annotations

from queue import Queue
from typing import TYPE_CHECKING

from griptape_nodes.exe_types.connections import Connections
from griptape_nodes.machines.dag_builder import DagBuilder

if TYPE_CHECKING:
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.machines.control_flow import ControlFlowMachine
    from griptape_nodes.retained_mode.managers.flow_manager import QueueItem


class WorkflowFlows:
    """The flows of one open workflow, how they nest, how their nodes connect, and the run in progress."""

    def __init__(self) -> None:
        # flow name -> its parent flow's name, None for the top-level flow (the canvas).
        self.name_to_parent_name: dict[str, str | None] = {}
        # The flows made by importing a referenced workflow, and that workflow's name.
        self.flow_to_referenced_workflow_name: dict[ControlFlow, str] = {}
        self.connections = Connections()

        # The run in progress, if any.
        self.global_flow_queue: Queue[QueueItem] = Queue()
        self.global_control_flow_machine: ControlFlowMachine | None = None
        self.global_single_node_resolution = False
        self.global_dag_builder = DagBuilder(self.connections)
