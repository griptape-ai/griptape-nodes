from __future__ import annotations

import importlib
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import semver

from griptape_nodes.retained_mode.events.app_events import (
    GetEngineVersionRequest,
    GetEngineVersionResultSuccess,
)
from griptape_nodes.retained_mode.events.library_events import (
    GetLibraryMetadataRequest,
    GetLibraryMetadataResultSuccess,
    GetNodeMetadataFromLibraryRequest,
    GetNodeMetadataFromLibraryResultSuccess,
    ListNodeTypesInLibraryRequest,
    ListNodeTypesInLibraryResultSuccess,
    ListRegisteredLibrariesRequest,
    ListRegisteredLibrariesResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.fitness_problems.libraries.deprecated_node_warning_problem import (
    DeprecatedNodeWarningProblem,
)
from griptape_nodes.retained_mode.managers.fitness_problems.workflows.deprecated_node_in_workflow_problem import (
    DeprecatedNodeInWorkflowProblem,
)
from griptape_nodes.retained_mode.managers.fitness_problems.workflows.node_type_not_found_problem import (
    NodeTypeNotFoundProblem,
)
from griptape_nodes.retained_mode.managers.library_lifecycle.library_status import LibraryStatus

if TYPE_CHECKING:
    from griptape_nodes.node_library.library_registry import LibrarySchema
    from griptape_nodes.node_library.workflow_registry import WorkflowMetadata
    from griptape_nodes.retained_mode.managers.event_manager import EventManager
    from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem
    from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem
    from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager

logger = logging.getLogger("griptape_nodes")


class LibraryVersionCompatibilityIssue(NamedTuple):
    """Represents a library version compatibility issue found in a library."""

    problem: LibraryProblem
    severity: LibraryStatus


class LibraryVersionCompatibilityCheck(ABC):
    """Abstract base class for library version compatibility checks."""

    @abstractmethod
    def applies_to_library(self, library_data: LibrarySchema) -> bool:
        """Return True if this check applies to the given library."""

    @abstractmethod
    def check_library(self, library_data: LibrarySchema) -> list[LibraryVersionCompatibilityIssue]:
        """Perform the library compatibility check."""


class WorkflowVersionCompatibilityIssue(NamedTuple):
    """Represents a workflow version compatibility issue found in a workflow."""

    problem: WorkflowProblem
    severity: WorkflowManager.WorkflowStatus


class WorkflowVersionCompatibilityCheck(ABC):
    """Abstract base class for workflow version compatibility checks."""

    @abstractmethod
    def applies_to_workflow(self, workflow_metadata: WorkflowMetadata) -> bool:
        """Return True if this check applies to the given workflow."""

    @abstractmethod
    def check_workflow(self, workflow_metadata: WorkflowMetadata) -> list[WorkflowVersionCompatibilityIssue]:
        """Perform the workflow compatibility check."""


class VersionCompatibilityManager:
    """Manages version compatibility checks for libraries and other components."""

    def __init__(self, event_manager: EventManager) -> None:
        self._event_manager = event_manager
        self._compatibility_checks: list[LibraryVersionCompatibilityCheck] = []
        self._workflow_compatibility_checks: list[WorkflowVersionCompatibilityCheck] = []
        self._discover_version_checks()

    def _discover_version_checks(self) -> None:
        """Automatically discover and register library and workflow version compatibility checks."""
        self._discover_library_version_checks()
        self._discover_workflow_version_checks()

    def _discover_library_version_checks(self) -> None:
        """Discover and register library version compatibility checks."""
        # Get the path to the version_compatibility/versions directory
        import griptape_nodes.version_compatibility.versions as versions_module

        versions_path = Path(versions_module.__file__).parent

        # Iterate through version directories
        for version_dir in versions_path.iterdir():
            if version_dir.is_dir() and not version_dir.name.startswith("__"):
                self._discover_checks_in_version_dir(version_dir)

    def _discover_workflow_version_checks(self) -> None:
        """Discover and register workflow version compatibility checks."""
        try:
            import griptape_nodes.version_compatibility.workflow_versions as workflow_versions_module

            workflow_versions_path = Path(workflow_versions_module.__file__).parent

            # Iterate through version directories
            for version_dir in workflow_versions_path.iterdir():
                if version_dir.is_dir() and not version_dir.name.startswith("__"):
                    self._discover_workflow_checks_in_version_dir(version_dir)
        except ImportError:
            # workflow_versions directory doesn't exist yet, skip discovery
            logger.debug("No workflow version compatibility checks directory found, skipping workflow check discovery")

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

    def _discover_workflow_checks_in_version_dir(self, version_dir: Path) -> None:
        """Discover workflow compatibility checks in a specific version directory."""
        # Iterate through Python files in the version directory
        for check_file in version_dir.glob("*.py"):
            if check_file.name.startswith("__"):
                continue

            # Import the module
            module_path = f"griptape_nodes.version_compatibility.workflow_versions.{version_dir.name}.{check_file.stem}"
            try:
                module = importlib.import_module(module_path)
            except ImportError as e:
                logger.debug("Failed to import workflow compatibility check module %s: %s", module_path, e)
                continue

            # Look for classes that inherit from WorkflowVersionCompatibilityCheck
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, WorkflowVersionCompatibilityCheck)
                    and attr is not WorkflowVersionCompatibilityCheck
                ):
                    check_instance = attr()
                    self._workflow_compatibility_checks.append(check_instance)
                    logger.debug("Registered workflow version compatibility check: %s", attr_name)

    def _check_library_for_deprecated_nodes(
        self, library_data: LibrarySchema
    ) -> list[LibraryVersionCompatibilityIssue]:
        """Check a library for deprecated nodes."""
        return [
            LibraryVersionCompatibilityIssue(
                problem=DeprecatedNodeWarningProblem(
                    display_name=node.metadata.display_name,
                    class_name=node.class_name,
                    removal_version=node.metadata.deprecation.removal_version,
                    deprecation_message=node.metadata.deprecation.deprecation_message,
                ),
                severity=LibraryStatus.FLAWED,
            )
            for node in library_data.nodes
            if node.metadata.deprecation is not None
        ] or []

    def check_library_version_compatibility(
        self, library_data: LibrarySchema
    ) -> list[LibraryVersionCompatibilityIssue]:
        """Check a library for version compatibility issues."""
        version_issues: list[LibraryVersionCompatibilityIssue] = []

        # Run all discovered compatibility checks
        for check_instance in self._compatibility_checks:
            if check_instance.applies_to_library(library_data):
                issues = check_instance.check_library(library_data)
                version_issues.extend(issues)

        version_issues.extend(self._check_library_for_deprecated_nodes(library_data))

        return version_issues

    def check_workflow_version_compatibility(
        self, workflow_metadata: WorkflowMetadata
    ) -> list[WorkflowVersionCompatibilityIssue]:
        """Check a workflow for version compatibility issues."""
        version_issues: list[WorkflowVersionCompatibilityIssue] = []

        # Run all discovered workflow compatibility checks
        for check_instance in self._workflow_compatibility_checks:
            if check_instance.applies_to_workflow(workflow_metadata):
                issues = check_instance.check_workflow(workflow_metadata)
                version_issues.extend(issues)

        # Check for deprecated nodes in the workflow
        version_issues.extend(self._check_workflow_for_deprecated_nodes(workflow_metadata))

        return version_issues

    def _check_workflow_for_deprecated_nodes(  # noqa: C901
        self, workflow_metadata: WorkflowMetadata
    ) -> list[WorkflowVersionCompatibilityIssue]:
        """Check a workflow for deprecated nodes.

        Examines each node type used in the workflow to determine if any are deprecated
        in their respective libraries. Returns warnings for deprecated nodes.
        """
        issues: list[WorkflowVersionCompatibilityIssue] = []

        # Get list of registered libraries once (silent check - no error logging)
        list_request = ListRegisteredLibrariesRequest()
        list_result = GriptapeNodes.LibraryManager().on_list_registered_libraries_request(list_request)

        if not isinstance(list_result, ListRegisteredLibrariesResultSuccess):
            # Should not happen, but handle gracefully - return empty issues
            return issues

        registered_libraries = list_result.libraries

        for library_name_and_node_type in workflow_metadata.node_types_used:
            library_name = library_name_and_node_type.library_name
            node_type = library_name_and_node_type.node_type

            # Check if library is registered
            if library_name not in registered_libraries:
                # Library not registered - skip this node silently, other checks handle missing libraries
                continue

            # Get library metadata to get version
            library_metadata_request = GetLibraryMetadataRequest(library=library_name)
            library_metadata_result = GriptapeNodes.LibraryManager().get_library_metadata_request(
                library_metadata_request
            )

            if not isinstance(library_metadata_result, GetLibraryMetadataResultSuccess):
                # Should not happen since we verified library exists, but handle gracefully
                continue

            current_library_version = library_metadata_result.metadata.library_version

            # Get workflow's saved library version
            workflow_library_version = None
            for lib_ref in workflow_metadata.node_libraries_referenced:
                if lib_ref.library_name == library_name:
                    workflow_library_version = lib_ref.library_version
                    break

            # Check if node type exists in library (silent check - no error logging)
            list_node_types_request = ListNodeTypesInLibraryRequest(library=library_name)
            list_node_types_result = GriptapeNodes.LibraryManager().on_list_node_types_in_library_request(
                list_node_types_request
            )

            if not isinstance(list_node_types_result, ListNodeTypesInLibraryResultSuccess):
                # Should not happen since we verified library exists, but handle gracefully
                continue

            if node_type not in list_node_types_result.node_types:
                # Node type doesn't exist in current library version
                issues.append(
                    WorkflowVersionCompatibilityIssue(
                        problem=NodeTypeNotFoundProblem(
                            node_type=node_type,
                            library_name=library_name,
                            current_library_version=current_library_version,
                            workflow_library_version=workflow_library_version,
                        ),
                        severity=GriptapeNodes.WorkflowManager().WorkflowStatus.FLAWED,
                    )
                )
                continue

            # Get node metadata from library (we know the node exists now)
            node_metadata_request = GetNodeMetadataFromLibraryRequest(library=library_name, node_type=node_type)
            node_metadata_result = GriptapeNodes.LibraryManager().get_node_metadata_from_library_request(
                node_metadata_request
            )

            if not isinstance(node_metadata_result, GetNodeMetadataFromLibraryResultSuccess):
                # Should not happen since we verified node exists, but handle gracefully
                continue

            node_metadata = node_metadata_result.metadata

            if node_metadata.deprecation is None:
                continue

            deprecation = node_metadata.deprecation

            # Create deprecated node problem
            issues.append(
                WorkflowVersionCompatibilityIssue(
                    problem=DeprecatedNodeInWorkflowProblem(
                        node_display_name=node_metadata.display_name,
                        node_type=node_type,
                        library_name=library_name,
                        current_library_version=current_library_version,
                        workflow_library_version=workflow_library_version,
                        removal_version=deprecation.removal_version,
                        deprecation_message=deprecation.deprecation_message,
                    ),
                    severity=GriptapeNodes.WorkflowManager().WorkflowStatus.FLAWED,
                )
            )

        return issues

    def _get_current_engine_version(self) -> semver.VersionInfo:
        """Get the current engine version."""
        result = GriptapeNodes.handle_request(GetEngineVersionRequest())
        if isinstance(result, GetEngineVersionResultSuccess):
            return semver.VersionInfo(major=result.major, minor=result.minor, patch=result.patch)
        msg = "Failed to get engine version"
        raise RuntimeError(msg)
