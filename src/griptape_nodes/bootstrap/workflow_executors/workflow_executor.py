import asyncio
import logging
from abc import abstractmethod
from typing import Any

from griptape_nodes.drivers.storage import StorageBackend

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    def __init__(self) -> None:
        self.output: dict | None = None

    def run(
        self,
        workflow_name: str,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
        **kwargs: Any,
    ) -> None:
        return asyncio.run(self.arun(workflow_name, flow_input, storage_backend, **kwargs))

    @abstractmethod
    async def arun(
        self,
        workflow_name: str,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
        **kwargs: Any,
    ) -> None: ...
