import argparse
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

LIBRARIES = ["REPLACE_LIBRARIES"]
PICKLE_DEFAULT = "REPLACE_PICKLE_DEFAULT"


logging.basicConfig(
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

load_dotenv()
os.environ["GTN_CONFIG_STORAGE_BACKEND"] = "gtc"


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


if __name__ == "__main__":
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
    flow_input = args.input
    pickle_result = args.pickle_control_flow_result

    try:
        flow_input = json.loads(flow_input) if flow_input else {}
    except Exception as e:
        msg = f"Error decoding JSON input: {e}"
        logger.info(msg)
        raise

    from structure_workflow_executor import StructureWorkflowExecutor
    from workflow import execute_workflow  # type: ignore[attr-defined]

    from griptape_nodes.drivers.storage import StorageBackend

    workflow_file_path = Path(__file__).parent / "workflow.py"
    workflow_runner = StructureWorkflowExecutor(storage_backend=StorageBackend("gtc"))

    _set_libraries(LIBRARIES)

    execute_workflow(input=flow_input, workflow_executor=workflow_runner, pickle_control_flow_result=pickle_result)
