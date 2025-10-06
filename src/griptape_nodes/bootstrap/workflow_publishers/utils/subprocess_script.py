import asyncio
import logging
from argparse import ArgumentParser

from griptape_nodes.bootstrap.workflow_publishers.local_workflow_publisher import LocalWorkflowPublisher

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


async def _main(
    workflow_name: str,
    workflow_path: str,
    publisher_name: str,
    published_workflow_file_name: str,
    *,
    pickle_control_flow_result: bool,
) -> None:
    local_publisher = LocalWorkflowPublisher()
    async with local_publisher as publisher:
        await publisher.arun(
            workflow_name=workflow_name,
            workflow_path=workflow_path,
            publisher_name=publisher_name,
            published_workflow_file_name=published_workflow_file_name,
            pickle_control_flow_result=pickle_control_flow_result,
        )

    msg = f"Published workflow to file: {published_workflow_file_name}"
    logger.info(msg)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--workflow-name",
        help="Name of the workflow to publish",
        required=True,
    )
    parser.add_argument(
        "--workflow-path",
        help="Path to the workflow file to publish",
        required=True,
    )
    parser.add_argument(
        "--publisher-name",
        help="Name of the publisher to use",
        required=True,
    )
    parser.add_argument(
        "--published-workflow-file-name", help="Name to use for the published workflow file", required=True
    )
    parser.add_argument(
        "--pickle-control-flow-result",
        action="store_true",
        default=False,
        help="Whether to pickle control flow results",
    )
    args = parser.parse_args()
    asyncio.run(
        _main(
            workflow_name=args.workflow_name,
            workflow_path=args.workflow_path,
            publisher_name=args.publisher_name,
            published_workflow_file_name=args.published_workflow_file_name,
            pickle_control_flow_result=args.pickle_control_flow_result,
        )
    )
