import argparse
import json
import logging

from dotenv import load_dotenv

from griptape_nodes.bootstrap.workflow_runners.bootstrap_workflow_runner import BootstrapWorkflowRunner

logging.basicConfig(
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

load_dotenv()


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
    parser.add_argument(
        "-s",
        "--storage-backend",
        default="local",
        help="The storage backend to use",
    )

    args = parser.parse_args()
    workflow_name = args.workflow_name
    flow_input = args.input
    storage_backend = args.storage_backend

    try:
        flow_input = json.loads(flow_input) if flow_input else {}
    except Exception as e:
        msg = f"Error decoding JSON input: {e}"
        logger.info(msg)
        raise

    workflow_runner = BootstrapWorkflowRunner()
    workflow_runner.run(
        workflow_path="workflow.py", workflow_name=workflow_name, flow_input=flow_input, storage_backend=storage_backend
    )
