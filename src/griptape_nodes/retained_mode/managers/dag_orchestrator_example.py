from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import networkx as nx

if TYPE_CHECKING:
    from concurrent.futures import Future

    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")

class NodeState(Enum):
    """Individual node execution states."""

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    CANCELED = "canceled"
    ERRORED = "errored"
    WAITING = "waiting"

# orchestrator attached to each flow, owned by griptape nodes
class DagOrchestrator:
    """Main DAG structure containing nodes and edges."""

    # The generated network of nodes
    network: nx.DiGraph
    # The node to reference mapping. Includes node and thread references.
    node_to_reference: dict[str, DagOrchestrator.DagNode]
    # The thread executor reference
    thread_executor: ThreadPoolExecutor
    sem: threading.Semaphore
    future_to_node: dict[Future, DagOrchestrator.DagNode]

    def __init__(self) -> None:
        """Initialize the DagOrchestrator singleton with initialization guard."""
        # Initialize only if our network hasn't been created yet (like GriptapeNodes pattern)
        self.network = nx.DiGraph()
        # Node to reference will also contain node state.
        self.node_to_reference = {}
        self.thread_executor = ThreadPoolExecutor()
        # Prevents a worker queue from developing
        self.sem = threading.Semaphore(self.thread_executor._max_workers)
        self.future_to_node = {}

    @dataclass(kw_only=True)
    class DagNode:
        """Represents a node in the DAG with runtime references."""

        node_reference: BaseNode
        thread_reference: Future | None = field(default=None)
        node_state: NodeState = field(default=NodeState.WAITING)

    def clear(self) -> None:
        self.network.clear()
        self.node_to_reference.clear()
        self.thread_executor.shutdown(wait=False, cancel_futures=True)
        self.future_to_node.clear()
