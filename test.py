import logging
import threading
import time
from multiprocessing import Queue as ProcessQueue

from dotenv import load_dotenv

from griptape_nodes.app.api import start_api
from griptape_nodes.app.app import _build_static_dir
from two_agent_workflow import execute_workflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

static_dir = _build_static_dir()
event_queue = ProcessQueue()
threading.Thread(target=start_api, args=(static_dir, event_queue), daemon=True).start()


def main() -> None:
    logger.info("Starting workflow execution 1...")
    first_output = execute_workflow(input={}, storage_backend="local")
    time.sleep(1)
    logger.info("Starting workflow execution 2...")
    second_output = execute_workflow(input={}, storage_backend="local")

    logger.info("Workflow execution 1 output")
    logger.info(first_output)

    logger.info("Workflow execution 2 output")
    logger.info(second_output)


if __name__ == "__main__":
    main()
