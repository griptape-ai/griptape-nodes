from __future__ import annotations

import importlib
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from griptape_nodes.retained_mode.events.app_events import (
    GetEngineVersionRequest,
    GetEngineVersionResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes, Version

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibrarySchema
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus

logger = logging.getLogger("griptape_nodes")


class LibraryVersionCompatibilityIssue(NamedTuple):
    """Represents a library version compatibility issue found in a library."""

    message: str
    severity: LibraryStatus


class LibraryVersionCompatibilityCheck(ABC):
    """Abstract base class for library version compatibility checks."""

    @abstractmethod
    def applies_to_library(self, library_data: LibrarySchema) -> bool:
        """Return True if this check applies to the given library."""

    @abstractmethod
    def check_library(self, library_data: LibrarySchema) -> list[LibraryVersionCompatibilityIssue]:
        """Perform the library compatibility check."""


class VersionCompatibilityManager:
    """Manages version compatibility checks for libraries and other components."""

    def __init__(self, event_manager: EventManager) -> None:
        self._event_manager = event_manager
        self._compatibility_checks: list[LibraryVersionCompatibilityCheck] = []
        self._discover_version_checks()

    def _discover_version_checks(self) -> None:
        """Automatically discover and register library version compatibility checks."""
        # Get the path to the version_compatibility/versions directory
        import griptape_nodes.version_compatibility.versions as versions_module

        versions_path = Path(versions_module.__file__).parent

        # Iterate through version directories
        for version_dir in versions_path.iterdir():
            if version_dir.is_dir() and not version_dir.name.startswith("__"):
                self._discover_checks_in_version_dir(version_dir)

    def _discover_checks_in_version_dir(self, version_dir: Path) -> None:
        """Discover compatibility checks in a specific version directory."""
        # Iterate through Python files in the version directory
        for check_file in version_dir.glob("*.py"):
            if check_file.name.startswith("__"):
                continue

            # Import the module
            module_path = f"griptape_nodes.version_compatibility.versions.{version_dir.name}.{check_file.stem}"
            module = importlib.import_module(module_path)

            # Look for classes that inherit from LibraryVersionCompatibilityCheck
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, LibraryVersionCompatibilityCheck)
                    and attr is not LibraryVersionCompatibilityCheck
                ):
                    check_instance = attr()
                    self._compatibility_checks.append(check_instance)
                    logger.debug("Registered library version compatibility check: %s", attr_name)

    def check_library_version_compatibility(
        self, library_data: LibrarySchema
    ) -> list[LibraryVersionCompatibilityIssue]:
        """Check a library for version compatibility issues."""
        version_issues = []

        # Run all discovered compatibility checks
        for check_instance in self._compatibility_checks:
            if check_instance.applies_to_library(library_data):
                issues = check_instance.check_library(library_data)
                version_issues.extend(issues)

        return version_issues

    def _get_current_engine_version(self) -> Version:
        """Get the current engine version."""
        result = GriptapeNodes.handle_request(GetEngineVersionRequest())
        if isinstance(result, GetEngineVersionResultSuccess):
            return Version(major=result.major, minor=result.minor, patch=result.patch)
        msg = "Failed to get engine version"
        raise RuntimeError(msg)
