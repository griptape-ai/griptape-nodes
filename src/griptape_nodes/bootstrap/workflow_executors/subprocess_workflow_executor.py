import asyncio
import threading
from multiprocessing import Process, Queue
from multiprocessing import Queue as ProcessQueue
from typing import Any

from griptape_nodes.app.api import start_api_async
from griptape_nodes.app.app import _build_static_dir
from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.drivers.storage.storage_backend import StorageBackend


class SubprocessWorkflowExecutor(WorkflowExecutor):
    @staticmethod
    def _subprocess_entry(
        exception_queue: Queue,
        workflow_name: str,
        flow_input: Any,
        workflow_path: str | None = None,
    ) -> None:
        try:
            static_dir = _build_static_dir()
            event_queue = ProcessQueue()

            # Start the API server in a thread using asyncio
            def run_api_server() -> None:
                asyncio.run(start_api_async(static_dir, event_queue))

            api_thread = threading.Thread(target=run_api_server, daemon=True)
            api_thread.start()

            workflow_runner = LocalWorkflowExecutor()
            asyncio.run(
                workflow_runner.run(workflow_name, flow_input, StorageBackend.LOCAL, workflow_path=workflow_path)
            )
        except Exception as e:
            exception_queue.put(e)
            raise

    def run(
        self,
        workflow_name: str,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,  # noqa: ARG002
        **kwargs: Any,
    ) -> None:
        workflow_path = kwargs.get("workflow_path")
        exception_queue = Queue()
        process = Process(
            target=self._subprocess_entry,
            args=(exception_queue, workflow_name, flow_input, workflow_path),
        )
        process.start()
        process.join()

        if not exception_queue.empty():
            exception = exception_queue.get_nowait()
            if isinstance(exception, Exception):
                raise exception
            msg = f"Expected an Exception but got: {type(exception)}"
            raise RuntimeError(msg)

        if process.exitcode != 0:
            msg = f"Process exited with code {process.exitcode} but no exception was raised."
            raise RuntimeError(msg)
