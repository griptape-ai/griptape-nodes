"""Utilities for safely instantiating throwaway node instances to introspect their parameters."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode


class NodeProbeError(Exception):
    """Raised when a throwaway probe node cannot be instantiated for parameter introspection.

    The string form is ``"<OriginalExceptionType>: <message>"`` so callers can surface a
    consistent, log-friendly cause across every probe call site.
    """

    def __init__(self, original: BaseException) -> None:
        super().__init__(f"{type(original).__name__}: {original}")
        self.original = original


def probe_node_class(node_class: type[BaseNode], *, name: str) -> BaseNode:
    """Instantiate a throwaway node so callers can read the parameters its ``__init__`` declares.

    The node is created without registering it with the ObjectManager or attaching it to a flow,
    so it is garbage-collected as soon as the caller releases its reference. Nodes whose
    ``__init__`` performs I/O (network calls, auth checks, disk reads) can raise; those errors
    are wrapped in ``NodeProbeError`` so every caller surfaces the same message format.

    Args:
        node_class: The node class to instantiate.
        name: Throwaway name to give the probe instance. Use a sentinel that won't collide with
            real node names (e.g. ``"__schema_probe__"``).

    Returns:
        The throwaway node instance.

    Raises:
        NodeProbeError: If the node class's ``__init__`` raised.
    """
    try:
        return node_class(name=name)
    except Exception as err:
        raise NodeProbeError(err) from err
