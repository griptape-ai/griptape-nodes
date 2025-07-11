from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import Library, LibrarySchema


class AdvancedNodeLibrary:
    """Base class for advanced node libraries with callback support.

    Library modules can inherit from this class to provide custom initialization
    and cleanup logic that runs before and after node loading.

    Example usage:
        ```python
        # In your library's advanced library module file:
        from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary

        class MyLibrary(AdvancedNodeLibrary):
            def before_library_nodes_loaded(self, library_data, library):
                # Set up any prerequisites before nodes are loaded
                print(f"About to load nodes for {library_data.name}")

            def after_library_nodes_loaded(self, library_data, library):
                # Perform any cleanup or additional setup after nodes are loaded
                print(f"Finished loading {len(library.get_registered_nodes())} nodes")
        ```
    """

    def before_library_nodes_loaded(self, library_data: LibrarySchema, library: Library) -> None:
        """Called before any nodes are loaded from the library.

        This method is called after the library instance is created but before
        any individual node classes are dynamically loaded and registered.

        Args:
            library_data: The library schema containing metadata and node definitions
            library: The library instance that will contain the loaded nodes
        """

    def after_library_nodes_loaded(self, library_data: LibrarySchema, library: Library) -> None:
        """Called after all nodes have been loaded from the library.

        This method is called after all node classes have been successfully
        loaded and registered with the library.

        Args:
            library_data: The library schema containing metadata and node definitions
            library: The library instance containing the loaded nodes
        """
