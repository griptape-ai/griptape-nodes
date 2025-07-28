import logging
import shutil
from pathlib import Path
from typing import Any

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger(__name__)


class CustomComponentManager:
    """Manages custom components by copying them to the static directory."""
    
    def __init__(self) -> None:
        self.config_manager = GriptapeNodes.ConfigManager()
        self.static_dir = self._get_static_directory()
        
    def _get_static_directory(self) -> Path:
        """Get the static files directory path."""
        workspace_path = self.config_manager.workspace_path
        static_files_directory = self.config_manager.get_config_value("static_files_directory", default="staticfiles")
        return workspace_path / static_files_directory
    
    def register_custom_components(self, library_path: Path) -> None:
        """Register custom components from a library by copying them to the static directory.
        
        Args:
            library_path: Path to the library directory containing custom components
        """
        try:
            # Read the library JSON to get custom component definitions
            library_json_path = library_path / "griptape_nodes_library.json"
            if not library_json_path.exists():
                logger.warning(f"Library JSON not found at {library_json_path}")
                return
                
            import json
            with open(library_json_path, 'r') as f:
                library_data = json.load(f)
            
            # Get custom components from the library
            custom_components = library_data.get("custom_components", [])
            
            for component in custom_components:
                self._register_custom_component(library_path, component)
                
        except Exception as e:
            logger.error(f"Failed to register custom components from {library_path}: {e}")
    
    def _register_custom_component(self, library_path: Path, component: dict[str, Any]) -> None:
        """Register a single custom component.
        
        Args:
            library_path: Path to the library directory
            component: Component definition from library JSON
        """
        try:
            name = component.get("name")
            file_path = component.get("file_path")
            description = component.get("description", "")
            
            if not name or not file_path:
                logger.warning(f"Invalid custom component definition: {component}")
                return
            
            # Construct the full path to the component file
            component_file_path = library_path / file_path
            
            if not component_file_path.exists():
                logger.warning(f"Custom component file not found: {component_file_path}")
                return
            
            # Create the static directory if it doesn't exist
            self.static_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy the component file to the static directory
            static_component_path = self.static_dir / f"custom_components/{name}.html"
            static_component_path.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.copy2(component_file_path, static_component_path)
            
            logger.info(f"Registered custom component '{name}' at {static_component_path}")
            
        except Exception as e:
            logger.error(f"Failed to register custom component {component}: {e}")
    
    def get_custom_component_url(self, component_name: str) -> str:
        """Get the URL for a custom component.
        
        Args:
            component_name: Name of the custom component
            
        Returns:
            URL to the custom component file
        """
        # The static server serves files at http://localhost:8124/static/
        return f"http://localhost:8124/static/custom_components/{component_name}.html" 