from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Self

from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.exe_types.node_types import EndNode, StartNode
from griptape_nodes.retained_mode.events.app_events import AppInitializationComplete
from griptape_nodes.retained_mode.events.base_events import (
    EventRequest,
    ExecutionGriptapeNodeEvent,
)
from griptape_nodes.retained_mode.events.execution_events import StartFlowRequest
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.events.workflow_events import (
    RunWorkflowFromScratchRequest,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

if TYPE_CHECKING:
    from types import TracebackType

logger = logging.getLogger(__name__)


class LocalExecutorError(Exception):
    """Exception raised during local workflow execution."""


class LocalWorkflowExecutor(WorkflowExecutor):
    def __init__(
        self,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
    ):
        super().__init__()
        self._set_storage_backend(storage_backend=storage_backend)

    async def __aenter__(self) -> Self:
        """Async context manager entry: initialize queue and broadcast app initialization."""
        GriptapeNodes.EventManager().initialize_queue()
        await GriptapeNodes.EventManager().broadcast_app_event(AppInitializationComplete())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        # TODO: Broadcast shutdown https://github.com/griptape-ai/griptape-nodes/issues/2149
        return

    def _get_workflow_name(self) -> str:
        try:
            context_manager = GriptapeNodes.ContextManager()
            return context_manager.get_current_workflow_name()
        except Exception as e:
            msg = f"Failed to get current workflow from context manager: {e}"
            logger.exception(msg)
            raise LocalExecutorError(msg) from e

    def _load_flow_for_workflow(self) -> str:
        try:
            context_manager = GriptapeNodes.ContextManager()
            return context_manager.get_current_flow().name
        except Exception as e:
            msg = f"Failed to get current flow from context manager: {e}"
            logger.exception(msg)
            raise LocalExecutorError(msg) from e

    def _set_storage_backend(self, storage_backend: StorageBackend) -> None:
        from griptape_nodes.retained_mode.managers.config_manager import ConfigManager

        try:
            config_manager = ConfigManager()
            config_manager.set_config_value(
                key="storage_backend",
                value=storage_backend,
            )
        except Exception as e:
            msg = f"Failed to set storage backend: {e}"
            logger.exception(msg)
            raise LocalExecutorError(msg) from e

    def _submit_output(self, output: dict) -> None:
        self.output = output

    async def _set_input_for_flow(self, flow_name: str, flow_input: dict[str, dict]) -> None:
        control_flow = GriptapeNodes.FlowManager().get_flow_by_name(flow_name)
        nodes = control_flow.nodes
        for node_name, node in nodes.items():
            if isinstance(node, StartNode):
                param_map: dict | None = flow_input.get(node_name)
                if param_map is not None:
                    for parameter_name, parameter_value in param_map.items():
                        set_parameter_value_request = SetParameterValueRequest(
                            parameter_name=parameter_name,
                            value=parameter_value,
                            node_name=node_name,
                        )
                        set_parameter_value_result = await GriptapeNodes.ahandle_request(set_parameter_value_request)

                        if set_parameter_value_result.failed():
                            msg = f"Failed to set parameter {parameter_name} for node {node_name}."
                            raise LocalExecutorError(msg)

    def _get_output_for_flow(self, flow_name: str) -> dict:
        control_flow = GriptapeNodes.FlowManager().get_flow_by_name(flow_name)
        nodes = control_flow.nodes
        output = {}
        for node_name, node in nodes.items():
            if isinstance(node, EndNode):
                output[node_name] = node.parameter_values
                # Parameter_output_values should also be included, and should take priority over parameter_values
                output[node_name].update(node.parameter_output_values)

        return output

    async def _load_workflow_from_path(self, workflow_path: str) -> None:
        """Load a workflow from a file path."""

        def _raise_load_error(msg: str) -> None:
            raise LocalExecutorError(msg)

        try:
            # Use the RunWorkflowFromScratchRequest to load the workflow
            request = RunWorkflowFromScratchRequest(file_path=workflow_path)
            result = await GriptapeNodes.ahandle_request(request)

            logger.info("Successfully loaded workflow from %s", workflow_path)
        except Exception as e:
            msg = f"Error loading workflow from path {workflow_path}: {e}"
            logger.exception(msg)
            raise LocalExecutorError(msg) from e

        if result.failed():
            msg = f"Failed to load workflow from path {workflow_path}"
            _raise_load_error(msg)

    async def _handle_event_request(self, event: EventRequest) -> None:
        """Handle EventRequest objects by processing them through GriptapeNodes."""
        await GriptapeNodes.ahandle_request(event.request)

    async def _handle_execution_event(
        self, event: ExecutionGriptapeNodeEvent, flow_name: str
    ) -> tuple[bool, Exception | None]:
        """Handle ExecutionGriptapeNodeEvent and return (is_finished, error)."""
        result_event = event.wrapped_event

        if type(result_event.payload).__name__ == "ControlFlowResolvedEvent":
            self._submit_output(self._get_output_for_flow(flow_name=flow_name))
            logger.info("Workflow finished!")
            return True, None
        if type(result_event.payload).__name__ == "ControlFlowCancelledEvent":
            msg = "Control flow cancelled"
            logger.error(msg)
            return True, LocalExecutorError(msg)

        return False, None

    async def aprepare_workflow_for_run(
        self,
        flow_input: Any,
        storage_backend: StorageBackend | None = None,
        **kwargs: Any,
    ) -> str:
        """Prepares a local workflow for execution.

        This method sets up the environment for executing a workflow, including
        initializing event listeners, registering libraries, loading the user-defined
        workflow, and preparing the specified workflow for execution.
        Parameters:
            flow_input: Input data for the flow, typically a dictionary.
            storage_backend: The storage backend to use for the workflow execution.

        Returns:
            str: The name of the prepared flow.
        """
        if storage_backend is not None:
            msg = "The storage_backend parameter is deprecated. Pass `storage_backend` to the constructor instead."
            raise ValueError(msg)

        GriptapeNodes.EventManager().initialize_queue()

        # Load workflow from file if workflow_path is provided
        workflow_path = kwargs.get("workflow_path")
        if workflow_path:
            await self._load_workflow_from_path(workflow_path)

        # Load the flow
        flow_name = self._load_flow_for_workflow()
        # Now let's set the input to the flow
        await self._set_input_for_flow(flow_name=flow_name, flow_input=flow_input)

        return flow_name

    async def arun(
        self,
        flow_input: Any,
        storage_backend: StorageBackend | None = None,
        **kwargs: Any,
    ) -> None:
        """Executes a local workflow.

        Executes a workflow by setting up event listeners, registering libraries,
        loading the user-defined workflow, and running the specified workflow.

        Parameters:
            workflow_name: The name of the workflow to execute.
            flow_input: Input data for the flow, typically a dictionary.
            storage_backend: The storage backend to use for the workflow execution.

        Returns:
            None
        """
        flow_name = await self.aprepare_workflow_for_run(
            flow_input=flow_input,
            storage_backend=storage_backend,
            **kwargs,
        )

        # Now send the run command to actually execute it
        pickle_control_flow_result = kwargs.get("pickle_control_flow_result", False)
        start_flow_request = StartFlowRequest(
            flow_name=flow_name, pickle_control_flow_result=pickle_control_flow_result
        )
        start_flow_result = await GriptapeNodes.ahandle_request(start_flow_request)

        if start_flow_result.failed():
            msg = f"Failed to start flow {flow_name}"
            raise LocalExecutorError(msg)

        logger.info("Workflow started!")

        # Wait for the control flow to finish
        is_flow_finished = False
        error: Exception | None = None

        event_queue = GriptapeNodes.EventManager().event_queue
        while not is_flow_finished:
            try:
                event = await event_queue.get()

                if isinstance(event, EventRequest):
                    await self._handle_event_request(event)
                elif isinstance(event, ExecutionGriptapeNodeEvent):
                    is_flow_finished, error = await self._handle_execution_event(event, flow_name)

                event_queue.task_done()

            except Exception as e:
                msg = f"Error handling queue event: {e}"
                logger.info(msg)

        if error is not None:
            raise error
