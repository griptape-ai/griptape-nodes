import importlib.util
import sys
import threading
from multiprocessing import Process, Queue
from multiprocessing import Queue as ProcessQueue
from pathlib import Path
from typing import Any

from griptape_nodes.app.api import start_api
from griptape_nodes.app.app import _build_static_dir
from griptape_nodes.bootstrap.workflow_executors.local_workflow_executor import LocalWorkflowExecutor
from griptape_nodes.bootstrap.workflow_executors.workflow_executor import WorkflowExecutor
from griptape_nodes.drivers.storage.storage_backend import StorageBackend
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class SubprocessWorkflowExecutor(WorkflowExecutor):
    @classmethod
    def load_workflow(cls, path_to_workflow: str) -> None:
        """Load a workflow from a file."""
        # Ensure file_path is a Path object
        file_path = Path(path_to_workflow)

        # Generate a unique module name
        module_name = f"gtn_dynamic_module_{file_path.name.replace('.', '_')}_{hash(str(file_path))}"

        # Load the module specification
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            msg = f"Could not load module specification from {file_path}"
            raise ImportError(msg)

        # Create the module
        module = importlib.util.module_from_spec(spec)

        # Add to sys.modules to handle recursive imports
        sys.modules[module_name] = module

        # Execute the module
        spec.loader.exec_module(module)

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
            threading.Thread(target=start_api, args=(static_dir, event_queue), daemon=True).start()

            if workflow_path:
                SubprocessWorkflowExecutor.load_workflow(workflow_path)
                context_manager = GriptapeNodes.ContextManager()
                workflow_name = context_manager.get_current_workflow_name()

            workflow_runner = LocalWorkflowExecutor()
            workflow_runner.run(workflow_name, flow_input, StorageBackend.LOCAL)
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
