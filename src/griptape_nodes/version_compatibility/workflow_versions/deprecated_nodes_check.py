"""Check for deprecated nodes in workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

import semver

from griptape_nodes.node_library.library_registry import LibraryNameAndVersion, LibraryRegistry
from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
    WorkflowVersionCompatibilityCheck,
    WorkflowVersionCompatibilityIssue,
)
from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager

if TYPE_CHECKING:
    from griptape_nodes.node_library.workflow_registry import WorkflowMetadata


class DeprecatedNodesCheck(WorkflowVersionCompatibilityCheck):
    """Check for deprecated nodes used in a workflow.

    Examines each node type used in the workflow to determine if any are deprecated
    in their respective libraries. Returns warnings for deprecated nodes.
    """

    def applies_to_workflow(self, workflow_metadata: WorkflowMetadata) -> bool:
        """Apply this check to all workflows that have node types listed."""
        return len(workflow_metadata.node_types_used) > 0

    def _get_workflow_library_version(
        self, node_libraries_referenced: list[LibraryNameAndVersion], library_name: str
    ) -> str | None:
        """Get the library version that the workflow was saved with."""
        for lib_ref in node_libraries_referenced:
            if lib_ref.library_name == library_name:
                return lib_ref.library_version
        return None

    def check_workflow(self, workflow_metadata: WorkflowMetadata) -> list[WorkflowVersionCompatibilityIssue]:  # noqa: C901, PLR0912
        """Check workflow for deprecated nodes."""
        issues: list[WorkflowVersionCompatibilityIssue] = []

        for library_name_and_node_type in workflow_metadata.node_types_used:
            library_name = library_name_and_node_type.library_name
            node_type = library_name_and_node_type.node_type

            # Missing libraries are caught by WorkflowManager.on_load_workflow_metadata_request
            # which adds problems for libraries that fail to load or register.
            # We skip deprecation checks for nodes in missing libraries.
            try:
                library = LibraryRegistry.get_library(library_name)
            except KeyError:
                continue

            # Get library metadata and versions
            library_metadata = library.get_metadata()
            current_library_version = library_metadata.library_version
            workflow_library_version = self._get_workflow_library_version(
                workflow_metadata.node_libraries_referenced, library_name
            )

            # Check if node type exists in the library
            try:
                node_metadata = library.get_node_metadata(node_type)
            except KeyError:
                # Node type doesn't exist in current library version
                message = f"This workflow uses node type '{node_type}' from library '{library_name}', but this node type is not found in the current library version {current_library_version}"

                if workflow_library_version:
                    message += f". The workflow was saved with library version {workflow_library_version}"

                message += ". This node may have been removed or renamed. Contact the library author for more details."

                issues.append(
                    WorkflowVersionCompatibilityIssue(
                        message=message,
                        severity=WorkflowManager.WorkflowStatus.FLAWED,
                    )
                )
                continue

            if node_metadata.deprecation is None:
                continue

            deprecation = node_metadata.deprecation

            removal_version_reached = False
            if deprecation.removal_version:
                try:
                    current_version = semver.VersionInfo.parse(current_library_version)
                    removal_version = semver.VersionInfo.parse(deprecation.removal_version)
                    removal_version_reached = current_version >= removal_version
                except Exception:
                    # Errored out trying to parse the version strings; assume not reached.
                    removal_version_reached = False

            # Build the complete message
            message = f"This workflow uses node '{node_metadata.display_name}' (class: {node_type}) from library '{library_name}', which is deprecated"

            if deprecation.removal_version:
                if removal_version_reached:
                    message += f" and was removed in version {deprecation.removal_version}"
                else:
                    message += f" and will be removed in version {deprecation.removal_version}"
            else:
                message += " and may be removed in future versions"

            message += f". You are currently using library version: {current_library_version}"

            if workflow_library_version:
                message += f", and the workflow was saved with library version: {workflow_library_version}"

            if deprecation.deprecation_message:
                message += f". The library author provided the following message for this deprecation: {deprecation.deprecation_message}"
            else:
                message += ". The library author did not provide a message explaining the deprecation."

            issues.append(
                WorkflowVersionCompatibilityIssue(
                    message=message,
                    severity=WorkflowManager.WorkflowStatus.FLAWED,
                )
            )

        return issues
