import logging
import threading
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Any

from griptape_nodes.app.app import _serve_static_server
from griptape_nodes.bootstrap.workflow_runners.local_workflow_runner import LocalWorkflowRunner
from griptape_nodes.bootstrap.workflow_runners.workflow_runner import WorkflowRunner


class SubprocessWorkflowRunner(WorkflowRunner):
    def __init__(self, libraries: list[Path]) -> None:
        self.libraries = libraries

    @staticmethod
    def _subprocess_entry(
        exception_queue: Queue,
        libraries: list[Path],
        workflow_path: str,
        workflow_name: str,
        flow_input: Any,
    ) -> None:
        # Reset logging to avoid duplicate logs in tests - this does not remove logs
        # because griptape nodes is doing some configuration of its own that seems
        # difficult to control.
        logger = logging.getLogger()
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        logger.setLevel(logging.NOTSET)

        try:
            threading.Thread(target=_serve_static_server, daemon=True).start()
            workflow_runner = LocalWorkflowRunner(libraries)
            workflow_runner.run(workflow_path, workflow_name, flow_input, "local")
        except Exception as e:
            exception_queue.put(e)
            raise

    def run(self, workflow_path: str, workflow_name: str, flow_input: Any, storage_backend: str = "local") -> None:  # noqa: ARG002
        exception_queue = Queue()
        process = Process(
            target=self._subprocess_entry,
            args=(exception_queue, self.libraries, workflow_path, workflow_name, flow_input),
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
