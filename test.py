import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Queue as ProcessQueue

from dotenv import load_dotenv

from griptape_nodes.app.api import start_api
from griptape_nodes.app.app import _build_static_dir
from griptape_nodes.machines.node_resolution import ExecuteNodeState
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from local_executor_test import execute_workflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

static_dir = _build_static_dir()
event_queue = ProcessQueue()
threading.Thread(target=start_api, args=(static_dir, event_queue), daemon=True).start()


def main() -> None:
    logger.info("Starting workflow execution 1...")
    logger.info("Initial thread count: %s", threading.active_count())
    first_output = execute_workflow(input={}, storage_backend="local")

    # Clean up background threads and resolution machines
    logger.info("Thread count after first execution: %s", threading.active_count())
    logger.info("Shutting down ThreadPoolExecutor to ensure all background threads complete...")
    ExecuteNodeState.executor.shutdown(wait=True)
    ExecuteNodeState.executor = ThreadPoolExecutor()

    # Reset the flow state before each execution
    from griptape_nodes.retained_mode.events.execution_events import UnresolveFlowRequest
    flow_name = GriptapeNodes.ContextManager().get_current_flow().name
    GriptapeNodes.handle_request(UnresolveFlowRequest(flow_name=flow_name))
    
    # Reset the global control flow machine to clear any remaining generators
    flow_manager = GriptapeNodes.FlowManager()
    if flow_manager._global_control_flow_machine is not None:
        logger.info("Resetting global control flow machine...")
        flow_manager._global_control_flow_machine.reset_machine()
        flow_manager._global_control_flow_machine = None
    
    logger.info("Cleanup complete, thread count: %s", threading.active_count())

    logger.info("Starting workflow execution 2...")
    second_output = execute_workflow(input={}, storage_backend="local")

    logger.info("Workflow execution 1 output")
    #logger.info(first_output)

    logger.info("Workflow execution 2 output")
    #logger.info(second_output)


if __name__ == "__main__":
    main()
