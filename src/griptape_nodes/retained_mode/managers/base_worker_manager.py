"""Abstract base class for worker lifecycle managers.

Worker managers control how worker subprocesses are created, acquired for node
execution, and shut down. Pluggable strategies (singleton, pool, ephemeral, etc.)
implement this interface without requiring changes to the executor or library manager.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from griptape_nodes.retained_mode.managers.base_worker_client import BaseWorkerClient


class BaseWorkerManager(ABC):
    """Manages the lifecycle of worker subprocesses for library isolation."""

    @abstractmethod
    async def register_library(
        self,
        library_name: str,
        worker_factory: Callable[[], Awaitable[BaseWorkerClient]],
    ) -> None:
        """Called when a library loads. The factory creates and starts a fresh worker.

        Singleton strategy calls it once and stores the result.
        Pool strategy calls it N times.
        Ephemeral strategy stores the factory for later on-demand use.
        """

    @abstractmethod
    async def unregister_library(self, library_name: str) -> None:
        """Called when a library unloads. Must stop all workers for this library."""

    @abstractmethod
    async def acquire_worker(self, library_name: str) -> BaseWorkerClient:
        """Return a worker ready to execute a node for this library.

        May return the existing worker, wait for a pool slot, or start a new one.
        Calls on_worker_crashed() if the stored worker is no longer running.
        Raises if no worker can be obtained.
        """

    @abstractmethod
    async def release_worker(self, library_name: str, worker: BaseWorkerClient) -> None:
        """Called after node execution (even if it raised). Manager decides reuse vs. discard."""

    @abstractmethod
    async def on_worker_crashed(self, library_name: str, worker: BaseWorkerClient) -> None:
        """Called by acquire_worker when the worker for a library is no longer running.

        Singleton strategy raises immediately (user must reload).
        Pool strategy may remove and replace the crashed worker.
        Ephemeral strategy is a no-op (workers are discarded after each use).
        """

    @abstractmethod
    async def stop_all(self) -> None:
        """Shut down all workers. Called on engine shutdown."""
