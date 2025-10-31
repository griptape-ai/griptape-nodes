import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

LIBRARIES = ["REPLACE_LIBRARIES"]
PICKLE_DEFAULT = "REPLACE_PICKLE_DEFAULT"
WEBHOOK_MODE_ARGS_COUNT = 4
START_FLOW_NODE_NAME = "Griptape Cloud Start Flow"


logging.basicConfig(
    level=logging.INFO,
)
logger = logging.getLogger("griptape_nodes")
logger.setLevel(logging.INFO)

load_dotenv()
os.environ["GTN_CONFIG_STORAGE_BACKEND"] = "gtc"
os.environ["GTN_ENABLE_WORKSPACE_FILE_WATCHING"] = "false"


def _set_libraries(libraries: list[str]) -> None:
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

    config_manager = GriptapeNodes.ConfigManager()
    config_manager.set_config_value(
        key="enable_workspace_file_watching",
        value=False,
    )
    config_manager.set_config_value(
        key="app_events.on_app_initialization_complete.libraries_to_register",
        value=libraries,
    )
    config_manager.set_config_value(
        key="workspace_directory",
        value=str(Path(__file__).parent),
    )


def _parse_webhook_args(raw_body: str, query_params_json: str, headers_json: str) -> tuple[dict, bool]:
    """Parse webhook arguments into flow input and pickle flag.

    Args:
        raw_body: The raw webhook body as a string
        query_params_json: Query parameters as a JSON string
        headers_json: Headers as a JSON string

    Returns:
        A tuple of (flow_input dict, pickle_result bool)
    """
    try:
        body_data = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        body_data = {"raw_body": raw_body}

    try:
        query_params = json.loads(query_params_json) if query_params_json else {}
    except json.JSONDecodeError:
        query_params = {}

    try:
        headers = json.loads(headers_json) if headers_json else {}
    except json.JSONDecodeError:
        headers = {}

    flow_input = {
        START_FLOW_NODE_NAME: {
            "payload": body_data,
            "query_params": query_params,
            "headers": headers,
        }
    }

    pickle_result = False

    return flow_input, pickle_result


def _parse_argparse_args() -> tuple[dict, bool]:
    """Parse command-line arguments using argparse.

    Returns:
        A tuple of (flow_input dict, pickle_result bool)
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i",
        "--input",
        default=None,
        help="The input to the flow",
    )
    parser.add_argument(
        "--pickle-control-flow-result",
        action="store_true",
        default=PICKLE_DEFAULT,
        help="Whether to pickle the control flow result",
    )

    args = parser.parse_args()
    flow_input_str = args.input
    pickle_result = args.pickle_control_flow_result

    try:
        flow_input = json.loads(flow_input_str) if flow_input_str else {}
    except json.JSONDecodeError as e:
        msg = f"Error decoding JSON input: {e}"
        logger.info(msg)
        raise

    return flow_input, pickle_result


if __name__ == "__main__":
    if len(sys.argv) == WEBHOOK_MODE_ARGS_COUNT and not any(arg.startswith("-") for arg in sys.argv[1:]):
        raw_body = sys.argv[1]
        query_params_json = sys.argv[2]
        headers_json = sys.argv[3]
        flow_input, pickle_result = _parse_webhook_args(raw_body, query_params_json, headers_json)
    else:
        flow_input, pickle_result = _parse_argparse_args()

    from structure_workflow_executor import StructureWorkflowExecutor
    from workflow import execute_workflow  # type: ignore[attr-defined]

    from griptape_nodes.drivers.storage import StorageBackend

    workflow_file_path = Path(__file__).parent / "workflow.py"
    workflow_runner = StructureWorkflowExecutor(storage_backend=StorageBackend("gtc"))

    _set_libraries(LIBRARIES)

    execute_workflow(input=flow_input, workflow_executor=workflow_runner, pickle_control_flow_result=pickle_result)
