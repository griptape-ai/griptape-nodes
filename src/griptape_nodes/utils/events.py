"""Event utilities for publishing events to the global event queue.

This module provides clean wrapper functions around the event queue functionality
with configurable queue support for different execution contexts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncio

# Module-level event queue - must be set by the application
_event_queue: asyncio.Queue | None = None


def set_event_queue(queue: asyncio.Queue | None) -> None:
    """Set the event queue for this module.

    Args:
        queue: The asyncio.Queue to use for events, or None to clear
    """
    global _event_queue  # noqa: PLW0603
    _event_queue = queue


def put_event(event: Any) -> None:
    """Put event into async queue from sync context (non-blocking).

    Args:
        event: The event to publish to the queue
    """
    if _event_queue is None:
        return

    _event_queue.put_nowait(event)


def put_event_threadsafe(loop: Any, event: Any) -> None:
    """Put event into async queue from sync context in a thread-safe manner.

    Args:
        loop: The asyncio event loop to use for thread-safe operation
        event: The event to publish to the queue
    """
    if _event_queue is None:
        return

    loop.call_soon_threadsafe(_event_queue.put_nowait, event)


async def aput_event(event: Any) -> None:
    """Put event into async queue from async context.

    Args:
        event: The event to publish to the queue
    """
    if _event_queue is None:
        return

    await _event_queue.put(event)
