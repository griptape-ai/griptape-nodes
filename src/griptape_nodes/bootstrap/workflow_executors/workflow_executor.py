import asyncio
import logging
from abc import abstractmethod
from types import TracebackType
from typing import Any, Self

from griptape_nodes.drivers.storage import StorageBackend

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    def __init__(self) -> None:
        self.output: dict | None = None

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        return

    def run(
        self,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
        **kwargs: Any,
    ) -> None:
        return asyncio.run(self.arun(flow_input, storage_backend, **kwargs))

    @abstractmethod
    async def arun(
        self,
        flow_input: Any,
        storage_backend: StorageBackend = StorageBackend.LOCAL,
        **kwargs: Any,
    ) -> None: ...
