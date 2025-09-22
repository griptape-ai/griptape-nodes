from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from griptape_nodes.node_library.library_registry import Library, LibraryRegistry
from griptape_nodes.utils.metaclasses import SingletonMeta

if TYPE_CHECKING:
    from griptape_nodes.exe_types.node_types import BaseNode
    from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary

logger = logging.getLogger("griptape_nodes")


class NodeExecutor(metaclass=SingletonMeta):
    """Simple singleton executor that draws methods from libraries and executes them dynamically."""
    advanced_libraries: dict[str, AdvancedNodeLibrary]

    def __init__(self) -> None:
        self._advanced_libraries = {}

    def load_library(self, library: Library) -> None:
        advanced_library = library.get_advanced_library()
        library_name = library.get_library_data().name
        if advanced_library is not None:
            self._advanced_libraries[library_name] = advanced_library

    def execute_method(self, method_name: str, library_name: str | None = None, *args: Any, **kwargs: Any) -> Any:
        """Execute a method by name with given arguments."""
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

    async def execute(self, node: BaseNode, library_name: str | None = None) -> None:
        """Execute the given node.

        Args:
            node: The BaseNode to execute
            library_name: The library that the execute method should come from.
        """
        try:
            # Get the node's library name
            if library_name is not None:
                library = LibraryRegistry.get_library(name=library_name)
            else:
                node_type = node.__class__.__name__
                library = LibraryRegistry.get_library_for_node_type(node_type=node_type)
            library_name = library.get_library_data().name
            # Execute using the node's specific library
            self.execute_method("execute", library_name, node)
        except KeyError:
            # Fallback to default node processing
            await node.aprocess()

    def refresh(self) -> None:
        self._advanced_libraries = {}
