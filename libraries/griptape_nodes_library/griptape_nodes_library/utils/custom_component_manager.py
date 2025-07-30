import logging
import shutil
from pathlib import Path
from typing import Any

from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.static_files_manager import StaticFilesManager

logger = logging.getLogger(__name__)


class CustomComponentManager:
    """Manages custom components by copying them to the static directory."""

    def __init__(self) -> None:
        self.config_manager = GriptapeNodes.ConfigManager()
        self.static_files_manager = StaticFilesManager(
            config_manager=self.config_manager, secrets_manager=GriptapeNodes.SecretsManager(), event_manager=None
        )
        self.static_dir = self.static_files_manager.get_static_directory()

    def register_custom_components(self, library_path: Path) -> None:
        """Register custom components from a library by copying them to the static directory.

        Args:
            library_path: Path to the library directory containing custom components
        """
        try:
            # Read the library JSON to get custom component definitions
            library_json_path = library_path / "griptape_nodes_library.json"
            if not library_json_path.exists():
                logger.warning("Library JSON not found at %s", library_json_path)
                return

            import json

            with library_json_path.open() as f:
                library_data = json.load(f)

            # Get custom components from the library
            custom_components = library_data.get("custom_components", [])

            for component in custom_components:
                self._register_custom_component(library_path, component)

            # Also copy the SDK file if it exists
            self._copy_sdk_file(library_path)

        except Exception as e:
            logger.error("Failed to register custom components from %s: %s", library_path, e)

    def _register_custom_component(self, library_path: Path, component: dict[str, Any]) -> None:
        """Register a single custom component.

        Args:
            library_path: Path to the library directory
            component: Component definition from library JSON
        """
        try:
            name = component.get("name")
            file_path = component.get("file_path")

            if not name or not file_path:
                logger.warning("Invalid custom component definition: %s", component)
                return

            # Construct the full path to the component file
            component_file_path = library_path / file_path

            if not component_file_path.exists():
                logger.warning("Custom component file not found: %s", component_file_path)
                return

            # Create the static directory if it doesn't exist
            self.static_dir.mkdir(parents=True, exist_ok=True)

            # Copy the component file to the static directory
            static_component_path = self.static_dir / f"custom_components/{name}.html"
            static_component_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(component_file_path, static_component_path)

            logger.info("Registered custom component '%s' at %s", name, static_component_path)

        except Exception as e:
            logger.error("Failed to register custom component %s: %s", component, e)

    def _copy_sdk_file(self, library_path: Path) -> None:
        """Copy the SDK file to the static directory.

        Args:
            library_path: Path to the library directory
        """
        try:
            sdk_file_path = library_path / "griptape_nodes_library/iframe-sdk.js"

            if not sdk_file_path.exists():
                logger.warning("SDK file not found at %s", sdk_file_path)
                return

            # Create the static directory if it doesn't exist
            self.static_dir.mkdir(parents=True, exist_ok=True)

            # Copy the SDK file to the static directory
            static_sdk_path = self.static_dir / "custom_components/iframe-sdk.js"
            static_sdk_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(sdk_file_path, static_sdk_path)

            logger.info("Copied SDK file to %s", static_sdk_path)

        except Exception as e:
            logger.error("Failed to copy SDK file: %s", e)

    def get_custom_component_url(self, component_name: str) -> str:
        """Get the URL for a custom component.

        Args:
            component_name: Name of the custom component

        Returns:
            URL to the custom component file
        """
        # The static server serves files at http://localhost:8124/static/
        return f"http://localhost:8124/static/custom_components/{component_name}.html"
