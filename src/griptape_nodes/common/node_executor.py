from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from collections.abc import Callable

    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")


class NodeExecutor(metaclass=SingletonMeta):
    """Simple singleton executor that draws methods from libraries and executes them dynamically."""

    def __init__(self) -> None:
        self._registry = LibraryRegistry()
        self._methods: dict[str, Callable] = {}
        self._loaded = False

    def _load_methods(self) -> None:
        """Load methods from registered libraries."""
        if self._loaded:
            return

        self._methods.clear()

        # Get all registered libraries
        for library_name in self._registry.list_libraries():
            try:
                library = self._registry.get_library(library_name)

                # Load methods from advanced library if available
                advanced_library = library.get_advanced_library()
                if advanced_library:
                    for attr_name in dir(advanced_library):
                        if not attr_name.startswith("_"):
                            attr = getattr(advanced_library, attr_name)
                            if callable(attr):
                                self._methods[attr_name] = attr

                logger.debug("Loaded methods from library: %s", library_name)

            except Exception as e:
                logger.error("Error loading methods from library %s: %s", library_name, e)

        self._loaded = True

    def execute_method(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a method by name with given arguments."""
        self._load_methods()

        if method_name not in self._methods:
            available = list(self._methods.keys())
            msg = f"Method '{method_name}' not found. Available: {available}"
            raise KeyError(msg)

        method = self._methods[method_name]
        logger.debug("Executing method: %s", method_name)

        try:
            return method(*args, **kwargs)
        except Exception as e:
            logger.error("Error executing method %s: %s", method_name, e)
            raise

    async def execute(self, node: BaseNode) -> None:
        """Execute the given node.

        Args:
            node: The BaseNode to execute
        """
        await node.aprocess()

    def refresh(self) -> None:
        """Refresh methods from libraries."""
        self._loaded = False
        self._load_methods()

    def list_methods(self) -> list[str]:
        """List all available methods."""
        self._load_methods()
        return list(self._methods.keys())
