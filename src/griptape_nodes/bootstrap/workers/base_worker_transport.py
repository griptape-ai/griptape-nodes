"""Abstract base class for the worker-subprocess IPC transport.

The worker subprocess reads requests from the parent and writes responses
through a transport. Concrete implementations supply the I/O channel
(stdin/stdout, socket, etc.) while the message-dispatch logic in
library_worker_entry.py depends only on this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseWorkerTransport(ABC):
    """Read/write interface for the worker subprocess IPC channel.

    Concrete implementations choose the I/O channel (stdin/stdout, socket,
    etc.) while the message-dispatch logic in library_worker_entry.py depends
    only on this interface.
    """

    @abstractmethod
    def read_message(self) -> dict | None:
        """Read and return the next JSON message from the parent.

        Returns None on EOF (parent closed the channel / shutdown).
        """

    @abstractmethod
    def write_message(self, msg: dict) -> None:
        """Serialize and send a JSON message to the parent."""
