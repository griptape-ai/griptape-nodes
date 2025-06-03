import importlib.util
import logging
import sys
from pathlib import Path
from queue import Queue
from typing import Any

from griptape.events import BaseEvent, EventBus, EventListener

from griptape_nodes.bootstrap.register_libraries_script import register_libraries
from griptape_nodes.bootstrap.workflow_runners.workflow_runner import WorkflowRunner
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


class LocalWorkflowRunner(WorkflowRunner):
    def __init__(self, libraries: list[Path]) -> None:
        self.registered_libraries = False
        self.libraries = libraries
        self.queue = Queue()

    def _load_user_workflow(self, path_to_workflow: str) -> None:
        # Ensure file_path is a Path object
        file_path = Path(path_to_workflow)

        # Generate a unique module name
        module_name = f"dynamic_module_{file_path.name.replace('.', '_')}_{hash(str(file_path))}"

        # Load the module specification
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            msg = f"Could not load module specification from {file_path}"
            raise ImportError(msg)

        # Create the module
        module = importlib.util.module_from_spec(spec)

        # Add to sys.modules to handle recursive imports
        sys.modules[module_name] = module

        # Execute the module
        spec.loader.exec_module(module)

    def _load_flow_for_workflow(self) -> str:
        context_manager = GriptapeNodes.ContextManager()
        return context_manager.get_current_flow().name

    def _set_storage_backend(self, storage_backend: str) -> None:
        from griptape_nodes.retained_mode.managers.config_manager import ConfigManager

        config_manager = ConfigManager()
        config_manager.set_config_value(
            key="storage_backend",
            value=storage_backend,
        )

    def _register_libraries(self) -> None:
        if not self.registered_libraries:
            register_libraries([str(p) for p in self.libraries])
            self.registered_libraries = True

    def _set_workflow_context(self, workflow_name: str) -> None:
        context_manager = GriptapeNodes.ContextManager()
        context_manager.push_workflow(workflow_name=workflow_name)

    def _handle_event(self, event: BaseEvent) -> None:
        try:
            if isinstance(event, GriptapeNodeEvent):
                self.__handle_node_event(event)
            elif isinstance(event, ExecutionGriptapeNodeEvent):
                self.__handle_execution_node_event(event)
            elif isinstance(event, ProgressEvent):
                self.__handle_progress_event(event)
            elif isinstance(event, AppEvent):
                self.__handle_app_event(event)
            else:
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
            GriptapeNodes.handle_request(event_request.request)

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
                            raise ValueError(msg)

    def _get_output_for_flow(self, flow_name: str) -> dict:
        control_flow = GriptapeNodes.FlowManager().get_flow_by_name(flow_name)
        nodes = control_flow.nodes
        output = {}
        for node_name, node in nodes.items():
            if isinstance(node, EndNode):
                output[node_name] = node.parameter_values

        return output

    def run(self, workflow_path: str, workflow_name: str, flow_input: Any, storage_backend: str = "local") -> None:
        """Executes a published workflow.

        Executes a workflow by setting up event listeners, registering libraries,
        loading the user-defined workflow, and running the specified workflow.

        Parameters:
            workflow_name: The name of the workflow to execute.
            flow_input: Input data for the flow, typically a dictionary.

        Returns:
            None
        """
        EventBus.add_event_listener(
            event_listener=EventListener(
                on_event=self._handle_event,
            )
        )

        # Set the storage backend
        self._set_storage_backend(storage_backend=storage_backend)

        # Register all of our relevant libraries
        self._register_libraries()

        # Required to set the workflow_context before loading the workflow
        # or nothing works. The name can be anything, but how about the workflow_name.
        self._set_workflow_context(workflow_name=workflow_name)
        self._load_user_workflow(workflow_path)
        flow_name = self._load_flow_for_workflow()
        # Now let's set the input to the flow
        self._set_input_for_flow(flow_name=flow_name, flow_input=flow_input)

        # Now send the run command to actually execute it
        start_flow_request = StartFlowRequest(flow_name=flow_name)
        start_flow_result = GriptapeNodes.handle_request(start_flow_request)

        if start_flow_result.failed():
            msg = f"Failed to start flow {workflow_name}"
            raise ValueError(msg)

        logger.info("Workflow started!")

        # Wait for the control flow to finish
        is_flow_finished = False
        error: Exception | None = None
        while not is_flow_finished:
            try:
                event = self.queue.get(block=True)

                if isinstance(event, ExecutionGriptapeNodeEvent):
                    result_event = event.wrapped_event

                    if type(result_event.payload).__name__ == "ControlFlowResolvedEvent":
                        self._submit_output(self._get_output_for_flow(flow_name=flow_name))
                        is_flow_finished = True
                        logger.info("Workflow finished!")
                    elif type(result_event.payload).__name__ == "ControlFlowCancelledEvent":
                        msg = "Control flow cancelled"
                        is_flow_finished = True
                        logger.error(msg)
                        error = ValueError(msg)

                self.queue.task_done()

            except Exception as e:
                msg = f"Error handling queue event: {e}"
                logger.info(msg)

        if error is not None:
            raise error
