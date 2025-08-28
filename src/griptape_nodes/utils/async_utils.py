"""Utilities for handling async/sync callback patterns."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


async def call_function(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call a function, handling both sync and async cases.

    Args:
        func: The function to call (sync or async)
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result of the function call
    """
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    return func(*args, **kwargs)
