"""Connections between engines on different machines, as WorkerManager uses them.

An engine whose distribution settings send a library's nodes to another machine has that machine's
engine start the library's worker in the artist's session. The worker then registers with the
artist's engine like a local worker, and every frame between the two passes through the machine's
engine, which relays it without handling it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from griptape_nodes.retained_mode.events.base_events import RequestPayload

# The version of the requests engines on different machines exchange. While it is 0.x, any
# difference is refused, since both machines also have to run the same engine version.
DISTRIBUTED_EXECUTION_SCHEMA_VERSION = "0.3.0"


class MachineNotFoundError(Exception):
    """Raised when a machine cannot be reached or stops answering, carrying why, written for an artist."""


class MachineLinks(Protocol):
    """The transport operations an engine needs to reach, and to serve, engines on other machines.

    A machine is named by its engine ID, as written in the distribution settings.
    """

    async def request(self, engine_id: str, request: RequestPayload, *, timeout_s: float | None) -> dict[str, Any]:
        """Send `request` to the engine `engine_id` and return its raw result payload.

        Args:
            engine_id: The engine to ask.
            request: What to ask it.
            timeout_s: How long to wait for the result, or None to wait until it arrives or the link
                to that engine is lost.

        Raises:
            MachineNotFoundError: The engine cannot be found or reached, did not answer within
                `timeout_s`, or its link was lost while waiting.
        """
        ...

    async def reach(self, worker_engine_id: str, *, via: str) -> None:
        """Send this engine's traffic for the worker `worker_engine_id` through the machine `via`.

        Raises:
            MachineNotFoundError: The machine cannot be found or reached.
        """
        ...

    async def relay(self, worker_engine_id: str, *, session_id: str) -> None:
        """Pass frames between the worker `worker_engine_id`, which this engine runs, and session `session_id`.

        Called by the machine that runs the worker, before it starts, so the worker's first frames
        already reach the artist's engine that owns the session.
        """
        ...

    async def forget(self, worker_engine_id: str) -> None:
        """Undo everything `reach` or `relay` set up for the worker. Forgetting an unknown worker does nothing."""
        ...

    def on_link_lost(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Call `callback` with an engine's ID once its link has been down longer than the heartbeat timeout."""
        ...
