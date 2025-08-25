import asyncio
from typing import Any

from griptape_nodes.app.api import start_api_async
from griptape_nodes.app.app import _build_static_dir
from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.drivers.storage.storage_backend import StorageBackend
from griptape_nodes.utils.events import set_event_queue


class AsyncWorkflowExecutor(WorkflowExecutor):
    """Async workflow executor that runs API server and workflow concurrently."""

    async def _start_api_server_task(self, static_dir: Any, event_queue: asyncio.Queue) -> None:
        """Start the API server as an async task."""
        await start_api_async(static_dir, event_queue)

    async def _run_workflow_task(
        self,
        workflow_name: str,
        flow_input: Any,
        workflow_path: str | None = None,
    ) -> None:
        """Run the workflow as an async task."""
        workflow_runner = LocalWorkflowExecutor()
        await workflow_runner.run(workflow_name, flow_input, StorageBackend.LOCAL, workflow_path=workflow_path)

    async def run(
        self,
        workflow_name: str,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,  # noqa: ARG002
        **kwargs: Any,
    ) -> None:
        """Async workflow execution with concurrent API server.

        Uses asyncio.TaskGroup to run the API server and workflow concurrently.
        The API server provides the necessary backend services while the workflow executes.
        """
        workflow_path = kwargs.get("workflow_path")

        # Prepare API server components
        static_dir = _build_static_dir()
        event_queue = asyncio.Queue()

        # Set the centralized event queue for this execution context
        set_event_queue(event_queue)

        # Use TaskGroup for clean concurrent execution and automatic cleanup
        async with asyncio.TaskGroup() as tg:
            # Start API server task (runs indefinitely)
            tg.create_task(self._start_api_server_task(static_dir, event_queue))

            # Start workflow task (completes when done)
            workflow_task = tg.create_task(self._run_workflow_task(workflow_name, flow_input, workflow_path))

            # Wait for workflow to complete
            # When workflow finishes, TaskGroup will automatically cancel API server
            await workflow_task
