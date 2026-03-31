"""SingletonWorkerManager: one persistent worker subprocess per library.

The worker is started once when the library loads and reused for all node
executions. If the worker crashes, acquire_worker raises immediately — the
user must reload the library.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.managers.base_worker_manager import BaseWorkerManager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from griptape_nodes.retained_mode.managers.base_worker_client import BaseWorkerClient

logger = logging.getLogger(__name__)


class SingletonWorkerManager(BaseWorkerManager):
    """One persistent worker subprocess per library."""

    def __init__(self) -> None:
        self._workers: dict[str, BaseWorkerClient] = {}

    async def register_library(
        self,
        library_name: str,
        worker_factory: Callable[[], Awaitable[BaseWorkerClient]],
    ) -> None:
        """Start a worker for the library and store it."""
        worker = await worker_factory()
        self._workers[library_name] = worker

    async def unregister_library(self, library_name: str) -> None:
        """Stop and discard the worker for this library."""
        worker = self._workers.pop(library_name, None)
        if worker is not None:
            try:
                await worker.stop()
            except Exception:
                logger.debug("Error stopping worker for library '%s'", library_name, exc_info=True)

    async def acquire_worker(self, library_name: str) -> BaseWorkerClient:
        """Return the stored worker for this library.

        Raises RuntimeError if no worker is registered or the worker has crashed.
        """
        worker = self._workers.get(library_name)
        if worker is None:
            msg = f"No worker registered for library '{library_name}'. The library may not have been loaded."
            raise RuntimeError(msg)
        if not worker.is_running():
            await self.on_worker_crashed(library_name, worker)
        return worker

    async def release_worker(self, library_name: str, worker: BaseWorkerClient) -> None:
        """No-op: the singleton worker is retained between executions."""

    async def on_worker_crashed(self, library_name: str, worker: BaseWorkerClient) -> None:  # noqa: ARG002
        """Raise immediately — the user must reload the library to get a new worker."""
        msg = (
            f"Worker subprocess for library '{library_name}' has crashed. "
            "Please reload the library to restart the worker."
        )
        raise RuntimeError(msg)

    async def stop_all(self) -> None:
        """Stop all running workers."""
        for library_name in list(self._workers):
            await self.unregister_library(library_name)
