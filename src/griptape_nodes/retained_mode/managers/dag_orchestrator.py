from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import networkx as nx

if TYPE_CHECKING:
    import threading
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
    """Main DAG structure containing nodes and edges for a specific flow."""

    # The generated network of nodes
    network: nx.DiGraph
    # The node to reference mapping. Includes node and thread references.
    node_to_reference: dict[str, DagOrchestrator.DagNode]
    sem: threading.Semaphore
    # Async execution support
    async_semaphore: asyncio.Semaphore
    task_to_node: dict[asyncio.Task, DagOrchestrator.DagNode]
    # The flow this orchestrator is associated with
    flow_name: str

    def __init__(self, flow_name: str, max_workers: int | None = None) -> None:
        """Initialize a DagOrchestrator for a specific flow.

        Args:
            flow_name: The name of the flow this orchestrator manages
            max_workers: Maximum number of worker threads (defaults to ThreadPoolExecutor default)
        """
        self.flow_name = flow_name
        self.network = nx.DiGraph()
        # Node to reference will also contain node state.
        self.node_to_reference = {}
        # Prevents a worker queue from developing
        # Async execution setup
        max_workers = max_workers if max_workers is not None else 5
        self.async_semaphore = asyncio.Semaphore(max_workers)
        self.task_to_node = {}

    @dataclass(kw_only=True)
    class DagNode:
        """Represents a node in the DAG with runtime references."""

        node_reference: BaseNode
        thread_reference: Future | None = field(default=None)
        task_reference: asyncio.Task | None = field(default=None)
        node_state: NodeState = field(default=NodeState.WAITING)

    def clear(self) -> None:
        """Clear the DAG state but keep the thread pool alive for reuse."""
        self.network.clear()
        self.node_to_reference.clear()
        # Cancel any pending tasks
        for task in list(self.task_to_node.keys()):
            if not task.done():
                task.cancel()
        self.task_to_node.clear()


class DagManager:
    """Manager for multiple DagOrchestrator instances, one per flow."""

    def __init__(self) -> None:
        """Initialize the DagManager."""
        self._flow_to_orchestrator: dict[str, DagOrchestrator] = {}
        self._max_workers: int | None = None

    def set_default_max_workers(self, max_workers: int | None) -> None:
        """Set the default maximum number of worker threads for new orchestrators.

        Args:
            max_workers: Maximum number of worker threads (None for ThreadPoolExecutor default)
        """
        self._max_workers = max_workers

    def get_orchestrator_for_flow(self, flow_name: str) -> DagOrchestrator:
        """Get or create a DagOrchestrator for the specified flow.

        Args:
            flow_name: The name of the flow

        Returns:
            DagOrchestrator: The orchestrator for the flow
        """
        if flow_name not in self._flow_to_orchestrator:
            logger.info("Creating new DagOrchestrator for flow '%s'", flow_name)
            self._flow_to_orchestrator[flow_name] = DagOrchestrator(flow_name, self._max_workers)

        return self._flow_to_orchestrator[flow_name]

    def remove_orchestrator_for_flow(self, flow_name: str) -> None:
        """Remove and shutdown the DagOrchestrator for the specified flow.

        Args:
            flow_name: The name of the flow
        """
        if flow_name in self._flow_to_orchestrator:
            del self._flow_to_orchestrator[flow_name]
            logger.info("Removed DagOrchestrator for flow '%s'", flow_name)

    def has_orchestrator_for_flow(self, flow_name: str) -> bool:
        """Check if a DagOrchestrator exists for the specified flow.

        Args:
            flow_name: The name of the flow

        Returns:
            bool: True if orchestrator exists for the flow
        """
        return flow_name in self._flow_to_orchestrator

    def clear_all_orchestrators(self) -> None:
        """Clear and shutdown all DagOrchestrator instances."""
        for flow_name in list(self._flow_to_orchestrator.keys()):
            self.remove_orchestrator_for_flow(flow_name)
        logger.info("Cleared all DagOrchestrators")

    def get_active_flows(self) -> list[str]:
        """Get a list of all flows that have active orchestrators.

        Returns:
            list[str]: List of active flow names
        """
        return list(self._flow_to_orchestrator.keys())
