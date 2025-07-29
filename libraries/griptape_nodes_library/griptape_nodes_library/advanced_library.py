from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import Library, LibrarySchema

logger = logging.getLogger(__name__)


class GriptapeNodesAdvancedLibrary(AdvancedNodeLibrary):
    """Advanced library implementation for Griptape Nodes Library.
    
    This class handles custom components and other advanced functionality
    for the Griptape Nodes Library.
    """

    def after_library_nodes_loaded(self, library_data: LibrarySchema, library: Library) -> None:
        """Called after all nodes have been loaded from the library.

        This method processes custom components defined in the library schema
        and makes them available for use.

        Args:
            library_data: The library schema containing metadata and node definitions
            library: The library instance containing the loaded nodes
        """
        if not library_data.components:
            logger.debug(f"No custom components found in library '{library_data.name}'")
            return

        logger.info(f"Processing {len(library_data.components)} custom components for library '{library_data.name}'")
        
        for component in library_data.components:
            self._process_component(component, library_data.name)

    def _process_component(self, component, library_name: str) -> None:
        """Process a single custom component.
        
        Args:
            component: The ComponentDefinition to process
            library_name: Name of the library for logging purposes
        """
        try:
            # For now, we'll just log the component details
            # In the future, this could involve:
            # - Validating the component path exists
            # - Registering the component with the UI system
            # - Setting up any necessary resources
            
            logger.info(f"Processing component '{component.name}' from library '{library_name}'")
            logger.debug(f"Component path: {component.path}")
            if component.description:
                logger.debug(f"Component description: {component.description}")
            
            # Check if the component path exists (for file-based components)
            if not component.path.startswith(('http://', 'https://', '//')):
                # This appears to be a file path
                component_path = Path(component.path)
                if not component_path.exists():
                    logger.warning(f"Component file not found: {component_path}")
                else:
                    logger.debug(f"Component file exists: {component_path}")
                    
        except Exception as e:
            logger.error(f"Error processing component '{component.name}': {e}") 