import logging
from queue import Queue
from typing import Any

from griptape.events import BaseEvent, EventBus, EventListener

from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.exe_types.node_types import EndNode, StartNode
from griptape_nodes.retained_mode.events.base_events import (
    AppEvent,
    EventRequest,
    ExecutionGriptapeNodeEvent,
    GriptapeNodeEvent,
    ProgressEvent,
)
from griptape_nodes.retained_mode.events.execution_events import SingleExecutionStepRequest, StartFlowRequest
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger(__name__)


class LocalExecutorError(Exception):
    """Exception raised during local workflow execution."""


class LocalWorkflowExecutor(WorkflowExecutor):
    def __init__(self) -> None:
        self.queue = Queue()
        self.output: dict | None = None

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

    def _handle_event(self, event: BaseEvent) -> None:
        try:
            match event:
                case GriptapeNodeEvent():
                    self.__handle_node_event(event)
                case ExecutionGriptapeNodeEvent():
                    self.__handle_execution_node_event(event)
                case ProgressEvent():
                    self.__handle_progress_event(event)
                case AppEvent():
                    self.__handle_app_event(event)
                case _:
                    msg = f"Unknown event type: {type(event)}"
                    logger.info(msg)
                    self.queue.put(event)
        except Exception as e:
            logger.info(e)

    def __handle_node_event(self, event: GriptapeNodeEvent) -> None:
        result_event = event.wrapped_event
        event_json = result_event.json()
        event_log = f"GriptapeNodeEvent: {event_json}"
        logger.info(event_log)

    def __handle_execution_node_event(self, event: ExecutionGriptapeNodeEvent) -> None:
        result_event = event.wrapped_event
        if type(result_event.payload).__name__ == "NodeStartProcessEvent":
            event_log = f"NodeStartProcessEvent: {result_event.payload}"
            logger.info(event_log)

        elif type(result_event.payload).__name__ == "ResumeNodeProcessingEvent":
            event_log = f"ResumeNodeProcessingEvent: {result_event.payload}"
            logger.info(event_log)

            # Here we need to handle the resume event since this is the callback mechanism
            # for the flow to be resumed for any Node that yields a generator in its process method.
            node_name = result_event.payload.node_name
            flow_name = GriptapeNodes.NodeManager().get_node_parent_flow_by_name(node_name)
            event_request = EventRequest(request=SingleExecutionStepRequest(flow_name=flow_name))
            self.queue.put(event_request)

        elif type(result_event.payload).__name__ == "NodeFinishProcessEvent":
            event_log = f"NodeFinishProcessEvent: {result_event.payload}"
            logger.info(event_log)

        else:
            event_log = f"ExecutionGriptapeNodeEvent: {result_event.payload}"
            logger.info(event_log)

        self.queue.put(event)

    def __handle_progress_event(self, gt_event: ProgressEvent) -> None:
        event_log = f"ProgressEvent: {gt_event}"
        logger.info(event_log)

    def __handle_app_event(self, event: AppEvent) -> None:
        event_log = f"AppEvent: {event.payload}"
        logger.info(event_log)

    def _submit_output(self, output: dict) -> None:
        self.output = output

    def _set_input_for_flow(self, flow_name: str, flow_input: dict[str, dict]) -> None:
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
                        set_parameter_value_result = GriptapeNodes.handle_request(set_parameter_value_request)

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

        return output

    def run(
        self,
        workflow_name: str,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
        **kwargs: Any,  # noqa: ARG002
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
        logger.info("Executing workflow: %s", workflow_name)

        EventBus.add_event_listener(
            event_listener=EventListener(
                on_event=self._handle_event,
            )
        )

        # Set the storage backend
        self._set_storage_backend(storage_backend=storage_backend)
        # Load the flow
        flow_name = self._load_flow_for_workflow()
        # Now let's set the input to the flow
        self._set_input_for_flow(flow_name=flow_name, flow_input=flow_input)

        # Now send the run command to actually execute it
        start_flow_request = StartFlowRequest(flow_name=flow_name)
        start_flow_result = GriptapeNodes.handle_request(start_flow_request)

        if start_flow_result.failed():
            msg = f"Failed to start flow {flow_name}"
            raise LocalExecutorError(msg)

        logger.info("Workflow started!")

        # Wait for the control flow to finish
        is_flow_finished = False
        error: Exception | None = None
        while not is_flow_finished:
            try:
                event = self.queue.get(block=True)

                if isinstance(event, EventRequest):
                    # Handle EventRequest objects by processing them through GriptapeNodes
                    request_payload = event.request
                    GriptapeNodes.handle_request(
                        request_payload, response_topic=event.response_topic, request_id=event.request_id
                    )
                elif isinstance(event, ExecutionGriptapeNodeEvent):
                    result_event = event.wrapped_event

                    if type(result_event.payload).__name__ == "ControlFlowResolvedEvent":
                        self._submit_output(self._get_output_for_flow(flow_name=flow_name))
                        is_flow_finished = True
                        logger.info("Workflow finished!")
                    elif type(result_event.payload).__name__ == "ControlFlowCancelledEvent":
                        msg = "Control flow cancelled"
                        is_flow_finished = True
                        logger.error(msg)
                        error = LocalExecutorError(msg)
                else:
                    logger.info("Unknown event type encountered: %s", type(event))

                self.queue.task_done()

            except Exception as e:
                msg = f"Error handling queue event: {e}"
                logger.info(msg)

        if error is not None:
            raise error
