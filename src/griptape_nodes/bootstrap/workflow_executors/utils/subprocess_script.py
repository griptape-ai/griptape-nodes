"""Subprocess script to execute a Griptape Nodes workflow.

This script is intended to be run as a subprocess by the SubprocessWorkflowExecutor.
"""

import json
from argparse import ArgumentParser

from workflow import execute_workflow  # type: ignore[attr-defined]

from griptape_nodes.bootstrap.workflow_executors.local_session_workflow_executor import LocalSessionWorkflowExecutor
from griptape_nodes.drivers.storage import StorageBackend
from griptape_nodes.utils import install_file_url_support

# Install file:// URL support for httpx/requests in subprocess
install_file_url_support()


def _main() -> None:
    parser = ArgumentParser()
    parser.add_argument(
        "--json-input",
        default=json.dumps({}),
        help="JSON string representing the flow input",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="ID of the session to use",
    )
    parser.add_argument(
        "--storage-backend",
        default="local",
        help="Storage backend to use",
    )
    parser.add_argument(
        "--workflow-path",
        default=None,
        help="Path to the Griptape Nodes workflow file",
    )
    parser.add_argument(
        "--pickle-control-flow-result",
        action="store_true",
        default=False,
        help="Whether to pickle control flow results",
    )
    parser.add_argument(
        "--save-on-failure",
        nargs="?",
        const="",
        default=None,
        help=(
            "On failure, save the current workflow state as a .py file. "
            "With no value: uses the project 'save_failed_workflow' situation. "
            "With a value: absolute or project-relative path."
        ),
    )
    args = parser.parse_args()
    flow_input = json.loads(args.json_input)

    local_session_workflow_executor = LocalSessionWorkflowExecutor(
        session_id=args.session_id,
        storage_backend=StorageBackend(args.storage_backend),
        save_on_failure_path=args.save_on_failure,
    )

    extra_kwargs: dict = {"save_on_failure_path": args.save_on_failure} if args.save_on_failure is not None else {}
    execute_workflow(
        input=flow_input,
        workflow_executor=local_session_workflow_executor,
        pickle_control_flow_result=args.pickle_control_flow_result,
        **extra_kwargs,
    )


if __name__ == "__main__":
    _main()
