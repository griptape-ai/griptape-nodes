from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode

logger = logging.getLogger("griptape_nodes")


class NodeExecutor(metaclass=SingletonMeta):
    """Simple singleton executor that draws methods from libraries and executes them dynamically."""

    def __init__(self) -> None:
        self._registry = LibraryRegistry()
        self._advanced_libraries: dict[str, Any] = {}
        self._loaded = False

    def _load_methods(self) -> None:
        """Load advanced library instances from registered libraries."""
        if self._loaded:
            return

        self._advanced_libraries.clear()

        # Get all registered libraries
        try:
            library_names = self._registry.list_libraries()
            logger.debug("Found %d registered libraries: %s", len(library_names), library_names)
        except Exception as e:
            logger.error("Error listing libraries: %s", e)
            library_names = []

        for library_name in library_names:
            try:
                library = self._registry.get_library(library_name)
                advanced_library = library.get_advanced_library()

                if advanced_library:
                    self._advanced_libraries[library_name] = advanced_library
                    logger.debug("Loaded advanced library for '%s': %s", library_name, type(advanced_library))
                else:
                    logger.debug("No advanced library found for '%s'", library_name)

            except Exception as e:
                logger.error("Error loading advanced library %s: %s", library_name, e)

        logger.info("NodeExecutor loaded %d advanced libraries", len(self._advanced_libraries))
        self._loaded = True

    def execute_method(self, method_name: str, *args: Any, library_name: str | None = None, **kwargs: Any) -> Any:
        """Execute a method by name with given arguments."""
        self._load_methods()

        if library_name and library_name in self._advanced_libraries:
            advanced_library = self._advanced_libraries[library_name]
            if hasattr(advanced_library, method_name):
                method = getattr(advanced_library, method_name)
                if callable(method):
                    logger.debug("Executing method '%s' from library '%s'", method_name, library_name)
                    return method(*args, **kwargs)
            msg = f"Method '{method_name}' not found in library '{library_name}'"
            raise KeyError(msg)

        msg = f"No library specified or library '{library_name}' not found"
        raise KeyError(msg)

    async def execute(self, node: BaseNode) -> None:
        """Execute the given node.

        Args:
            node: The BaseNode to execute
        """
        try:
            # Get the node's library name
            node_type = node.__class__.__name__
            library = self._registry.get_library_for_node_type(node_type)
            library_name = library.get_library_data().name

            # Execute using the node's specific library
            self.execute_method("execute", node, library_name=library_name)
        except KeyError:
            # Fallback to default node processing
            await node.aprocess()

    def refresh(self) -> None:
        """Refresh methods from libraries."""
        self._loaded = False
        self._load_methods()
