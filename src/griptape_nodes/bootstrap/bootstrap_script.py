import argparse
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from queue import Queue
from typing import Any

from dotenv import load_dotenv
from griptape.artifacts import TextArtifact
from griptape.drivers.event_listener.griptape_cloud_event_listener_driver import GriptapeCloudEventListenerDriver
from griptape.events import BaseEvent, EventBus, EventListener, FinishStructureRunEvent
from register_libraries_script import (  # type: ignore[import] - This import is used in the runtime environment
    PATHS,
    register_libraries,
)

from griptape_nodes.exe_types.flow import ControlFlow
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

logging.basicConfig(
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

load_dotenv()

queue = Queue()


def _load_user_workflow(path_to_workflow: str) -> None:
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


def _load_flow_for_workflow() -> ControlFlow:
    context_manager = GriptapeNodes.ContextManager()
    return context_manager.get_current_flow()


def _set_workflow_context(workflow_name: str) -> None:
    context_manager = GriptapeNodes.ContextManager()
    context_manager.push_workflow(workflow_name=workflow_name)


def _handle_event(event: BaseEvent) -> None:
    try:
        if isinstance(event, GriptapeNodeEvent):
            __handle_node_event(event)
        elif isinstance(event, ExecutionGriptapeNodeEvent):
            __handle_execution_node_event(event)
        elif isinstance(event, ProgressEvent):
            __handle_progress_event(event)
        elif isinstance(event, AppEvent):
            __handle_app_event(event)
        else:
            msg = f"Unknown event type: {type(event)}"
            logger.info(msg)
            queue.put(event)
    except Exception as e:
        logger.info(e)


def __handle_node_event(event: GriptapeNodeEvent) -> None:
    result_event = event.wrapped_event
    event_json = result_event.json()
    event_log = f"GriptapeNodeEvent: {event_json}"
    logger.info(event_log)


def __handle_execution_node_event(event: ExecutionGriptapeNodeEvent) -> None:
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

    queue.put(event)


def __handle_progress_event(gt_event: ProgressEvent) -> None:
    event_log = f"ProgressEvent: {gt_event}"
    logger.info(event_log)


def __handle_app_event(event: AppEvent) -> None:
    event_log = f"AppEvent: {event.payload}"
    logger.info(event_log)


def _submit_output(output: dict) -> None:
    if "GT_CLOUD_STRUCTURE_RUN_ID" in os.environ:
        kwargs: dict = {
            "batched": False,
        }
        if "GT_CLOUD_BASE_URL" in os.environ:
            base_url = os.environ["GT_CLOUD_BASE_URL"]
            if "http://localhost" in base_url or "http://127.0.0.1" in base_url:
                kwargs["headers"] = {}
        gtc_event_listener = GriptapeCloudEventListenerDriver(**kwargs)
        gtc_event_listener.try_publish_event_payload(
            FinishStructureRunEvent(output_task_output=TextArtifact(json.dumps(output))).to_dict()
        )


def _set_input_for_flow(flow_name: str, flow_input: dict[str, dict]) -> None:
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


def _get_output_for_flow(flow_name: str) -> dict:
    control_flow = GriptapeNodes.FlowManager().get_flow_by_name(flow_name)
    nodes = control_flow.nodes
    output = {}
    for node_name, node in nodes.items():
        if isinstance(node, EndNode):
            output[node_name] = node.parameter_values

    return output


def run(workflow_name: str, flow_input: Any) -> None:
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
            on_event=_handle_event,
        )
    )

    # Register all of our relevant libraries
    register_libraries(PATHS)

    # Required to set the workflow_context before loading the workflow
    # or nothing works. The name can be anything, but how about the workflow_name.
    _set_workflow_context(workflow_name=workflow_name)
    _load_user_workflow("workflow.py")
    flow = _load_flow_for_workflow()
    flow_name = flow.name
    # Now let's set the input to the flow
    _set_input_for_flow(flow_name=flow_name, flow_input=flow_input)

    # Now send the run command to actually execute it
    start_flow_request = StartFlowRequest(flow_name=flow_name)
    start_flow_result = GriptapeNodes.handle_request(start_flow_request)

    if start_flow_result.failed():
        msg = f"Failed to start flow {workflow_name}"
        raise ValueError(msg)

    logger.info("Workflow started!")

    # Wait for the control flow to finish
    is_flow_finished = False
    while not is_flow_finished:
        try:
            event = queue.get(block=True)
            if isinstance(event, ExecutionGriptapeNodeEvent):
                result_event = event.wrapped_event

                if type(result_event.payload).__name__ == "ControlFlowResolvedEvent":
                    _submit_output(_get_output_for_flow(flow_name=flow_name))
                    is_flow_finished = True
                    logger.info("Workflow finished!")

            queue.task_done()

        except Exception as e:
            msg = f"Error handling queue event: {e}"
            logger.info(msg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-n",
        "--workflow-name",
        default=None,
        help="Set the Flow Name to run",
    )
    parser.add_argument(
        "-i",
        "--input",
        default=None,
        help="The input to the flow",
    )

    args = parser.parse_args()
    workflow_name = args.workflow_name
    flow_input = args.input

    try:
        flow_input = json.loads(flow_input) if flow_input else {}
    except Exception as e:
        msg = f"Error decoding JSON input: {e}"
        logger.info(msg)
        raise

    run(workflow_name=workflow_name, flow_input=flow_input)
