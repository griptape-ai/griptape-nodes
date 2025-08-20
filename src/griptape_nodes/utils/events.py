"""Event utilities for publishing events to the global event queue.

This module provides clean wrapper functions around the event queue functionality
while handling the lazy import internally to avoid circular imports.
"""

from __future__ import annotations

from typing import Any


def put_event(event: Any) -> None:
    """Put event into async queue from sync context (non-blocking).

    Args:
        event: The event to publish to the queue
    """
    # Lazy import to avoid circular imports
    from griptape_nodes.app.app import put_event as _put_event

    _put_event(event)


async def aput_event(event: Any) -> None:
    """Put event into async queue from async context.

    Args:
        event: The event to publish to the queue
    """
    # Lazy import to avoid circular imports
    from griptape_nodes.app.app import aput_event as _aput_event

    await _aput_event(event)
