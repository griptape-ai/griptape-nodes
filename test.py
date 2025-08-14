import gc
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Queue as ProcessQueue

from dotenv import load_dotenv

from two_agent_no_image import execute_workflow
from griptape_nodes.app.api import start_api
from griptape_nodes.app.app import _build_static_dir
from griptape_nodes.machines.node_resolution import ExecuteNodeState
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

static_dir = _build_static_dir()
event_queue = ProcessQueue()
threading.Thread(target=start_api, args=(static_dir, event_queue), daemon=True).start()


def kill_threads_except_main_and_thread2() -> None:
    """Kill all threads except main thread and thread-2."""
    current_threads = threading.enumerate()
    main_thread = threading.main_thread()

    logger.info("Current threads before cleanup: %s", [(t.name, t.ident, t.daemon) for t in current_threads])

    for thread in current_threads:
        # Skip main thread and thread-2
        if thread == main_thread or thread.name == "thread-2":
            continue

        # For daemon threads, just set them as non-daemon (they'll die when main exits)
        if thread.daemon:
            continue

        # For non-daemon threads that are still alive
        if thread.is_alive():
            logger.info("Attempting to join thread: %s", thread.name)
            # Try to join with timeout
            try:
                thread.join(timeout=1.0)
                if thread.is_alive():
                    logger.warning("Thread %s did not terminate within timeout", thread.name)
            except Exception as e:
                logger.warning("Error joining thread %s: %s", thread.name, e)

    # Force garbage collection to clean up thread references
    gc.collect()

    remaining_threads = threading.enumerate()
    logger.info("Remaining threads after cleanup: %s", [(t.name, t.ident, t.daemon) for t in remaining_threads])


def main() -> None:
    logger.info("Starting workflow execution 1...")
    logger.info("Initial thread count: %s", threading.active_count())
    execute_workflow(input={}, storage_backend="local")

    # Clean up background threads and resolution machines
    # logger.info("Thread count after first execution: %s", threading.active_count())
    # logger.info("Shutting down ThreadPoolExecutor to ensure all background threads complete...")
    # ExecuteNodeState.executor.shutdown(wait=True)
    # ExecuteNodeState.executor = ThreadPoolExecutor()

    # Reset the flow state before each execution
    # from griptape_nodes.retained_mode.events.execution_events import UnresolveFlowRequest

    # flow_name = GriptapeNodes.ContextManager().get_current_flow().name
    # GriptapeNodes.handle_request(UnresolveFlowRequest(flow_name=flow_name))

    # # Reset the global control flow machine to clear any remaining generators
    # flow_manager = GriptapeNodes.FlowManager()
    # if flow_manager._global_control_flow_machine is not None:
    #     logger.info("Resetting global control flow machine...")
    #     flow_manager._global_control_flow_machine.reset_machine()
    #     flow_manager._global_control_flow_machine = None

    # # Kill threads except main thread and thread-2
    # kill_threads_except_main_and_thread2()

    # Optional: wait a moment for cleanup
    time.sleep(0.1)

    #logger.info("Cleanup complete, thread count: %s", threading.active_count())

    logger.info("Starting workflow execution 2...")
    execute_workflow(input={}, storage_backend="local")
    time.sleep(0.1)

    logger.info("starting workflow execution 3...")
    execute_workflow(input={}, storage_backend="local")

    logger.info("Workflow execution 1 output")
    # logger.info(first_output)

    logger.info("Workflow execution 2 output")
    # logger.info(second_output)


if __name__ == "__main__":
    main()
