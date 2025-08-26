import logging
from typing import Any

from griptape_nodes.drivers.storage import StorageBackend

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    async def run(
        self,
        workflow_name: str,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
        **kwargs: Any,
    ) -> None:
        msg = "Subclasses must implement the run method"
        raise NotImplementedError(msg)

    async def arun(
        self,
        workflow_name: str,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
        **kwargs: Any,
    ) -> None:
        await self.run(workflow_name, flow_input, storage_backend, **kwargs)
