from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.events.execution_events import (
    CreateExecutionMachineRequest,
    CreateExecutionMachineResultSuccess,
)
from griptape_nodes.retained_mode.managers.dag_orchestrator import DagOrchestrator

if TYPE_CHECKING:
    from griptape_nodes.machines.control_flow import ControlFlowMachine
    from griptape_nodes.retained_mode.events.base_events import ResultPayload
    from griptape_nodes.retained_mode.managers.event_manager import EventManager

logger = logging.getLogger("griptape_nodes")


class ExecutionMachineManager:
    """Manager for multiple machine instances, one per flow."""

    def __init__(self, event_manager: EventManager) -> None:
        """Initialize the ExecutionMachineManager."""
        event_manager.assign_manager_to_request_type(CreateExecutionMachineRequest, self.on_create_machine_request)
        self._flow_to_machine: dict[str, ControlFlowMachine] = {}
        # Could consider moving this to be on the machine itself.
        self._machine_to_orchestrator: dict[ControlFlowMachine, DagOrchestrator] = {}
        self._max_workers: int | None = None

    @property
    def max_workers(self) -> int | None:
        return self._max_workers

    @max_workers.setter
    def max_workers(self, max_workers: int | None) -> None:
        """Set the default maximum number of worker threads for new orchestrators.

        Args:
            max_workers: Maximum number of worker threads (None for ThreadPoolExecutor default)
        """
        self._max_workers = max_workers

    def on_create_machine_request(self, request: CreateExecutionMachineRequest) -> ResultPayload:
        """Get or create a ControlFlowMachine for the specified flow.

        Args:
            request: The request to create the machine.

        Returns:
            ControlFlowMachine: The machine for the flow
        """
        flow_name = request.flow_name
        if flow_name is None:
            msg = "Flow name is required"
            raise ValueError(msg)

        # Get current parallel execution setting from config
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        in_parallel = GriptapeNodes.ConfigManager().get_config_value("parallel_execution", default=False)

        # Check if we need to recreate the machine due to config change
        needs_recreation = False
        if flow_name in self._flow_to_machine:
            existing_machine = self._flow_to_machine[flow_name]
            # Check if the existing machine's parallel setting matches current config
            # The machine stores this in its context's resolution_machine type
            from griptape_nodes.machines.parallel_resolution import ParallelResolutionMachine

            is_currently_parallel = isinstance(existing_machine.get_resolution_machine(), ParallelResolutionMachine)
            if is_currently_parallel != in_parallel:
                logger.info(
                    "Config changed for flow '%s': was parallel=%s, now parallel=%s. Recreating machine.",
                    flow_name,
                    is_currently_parallel,
                    in_parallel,
                )
                # Remove old machine and its orchestrator
                if existing_machine in self._machine_to_orchestrator:
                    del self._machine_to_orchestrator[existing_machine]
                del self._flow_to_machine[flow_name]
                needs_recreation = True

        if flow_name not in self._flow_to_machine or needs_recreation:
            logger.info("Creating new ControlFlowMachine for flow '%s' (parallel=%s)", flow_name, in_parallel)

            from griptape_nodes.machines.control_flow import ControlFlowMachine

            if in_parallel:
                orchestrator = DagOrchestrator(flow_name, self._max_workers)
            else:
                orchestrator = None
            machine = ControlFlowMachine(flow_name, in_parallel=in_parallel, dag_orchestrator=orchestrator)
            self._flow_to_machine[flow_name] = machine
            # Create corresponding orchestrator
            if orchestrator is not None:
                self._machine_to_orchestrator[machine] = orchestrator

        result = CreateExecutionMachineResultSuccess(machine=self._flow_to_machine[flow_name])
        return result

    def get_machine_for_flow(self, flow_name: str) -> ControlFlowMachine:
        """Get or create a ControlFlowMachine for the specified flow.

        Delegates to on_create_machine_request to ensure consistent behavior.

        Args:
            flow_name: The name of the flow

        Returns:
            ControlFlowMachine: The machine for the flow
        """
        # Use the same logic as on_create_machine_request
        request = CreateExecutionMachineRequest(flow_name=flow_name)
        result = self.on_create_machine_request(request)

        if isinstance(result, CreateExecutionMachineResultSuccess):
            return result.machine
        msg = f"Failed to get or create machine for flow '{flow_name}'"
        raise RuntimeError(msg)

    def remove_machine_for_flow(self, flow_name: str) -> None:
        """Remove the ControlFlowMachine and its DagOrchestrator for the specified flow.

        Args:
            flow_name: The name of the flow
        """
        if flow_name in self._flow_to_machine:
            machine = self._flow_to_machine[flow_name]
            # Clear orchestrator if exists
            if machine in self._machine_to_orchestrator:
                orchestrator = self._machine_to_orchestrator[machine]
                orchestrator.clear()
                del self._machine_to_orchestrator[machine]
            del self._flow_to_machine[flow_name]
            logger.info("Removed ControlFlowMachine and DagOrchestrator for flow '%s'", flow_name)

    def has_machine_for_flow(self, flow_name: str) -> bool:
        """Check if a ControlFlowMachine exists for the specified flow.

        Args:
            flow_name: The name of the flow

        Returns:
            bool: True if machine exists for the flow
        """
        return flow_name in self._flow_to_machine

    def clear_all_machines(self) -> None:
        """Clear and shutdown all ControlFlowMachine and DagOrchestrator instances."""
        for flow_name in list(self._flow_to_machine.keys()):
            self.remove_machine_for_flow(flow_name)
        logger.info("Cleared all ControlFlowMachines and DagOrchestrators")

    @property
    def get_active_flows(self) -> list[str]:
        """Get a list of all flows that have active machines.

        Returns:
            list[str]: List of active flow names
        """
        return list(self._flow_to_machine.keys())

    def get_orchestrator_for_machine(self, machine: ControlFlowMachine) -> DagOrchestrator | None:
        """Get the DagOrchestrator associated with a ControlFlowMachine.

        Args:
            machine: The ControlFlowMachine instance

        Returns:
            DagOrchestrator | None: The orchestrator if exists, None otherwise
        """
        return self._machine_to_orchestrator.get(machine)

    def get_orchestrator_for_flow(self, flow_name: str) -> DagOrchestrator | None:
        """Get or create a DagOrchestrator for the specified flow.

        Returns None if parallel execution is disabled.

        Args:
            flow_name: The name of the flow

        Returns:
            DagOrchestrator | None: The orchestrator for the flow, or None if parallel execution is disabled
        """
        machine = self.get_machine_for_flow(flow_name)

        # Check if parallel execution is enabled
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

        in_parallel = GriptapeNodes.ConfigManager().get_config_value("parallel_execution", default=False)
        if not in_parallel:
            return None

        if machine not in self._machine_to_orchestrator:
            # Create orchestrator if it doesn't exist
            orchestrator = DagOrchestrator(flow_name, self._max_workers)
            self._machine_to_orchestrator[machine] = orchestrator
        return self._machine_to_orchestrator[machine]
