"""Schema compatibility check for workflows missing the --save-on-failure argument."""

from __future__ import annotations

from typing import TYPE_CHECKING

import semver

from griptape_nodes.retained_mode.events.workflow_events import WorkflowStatus
from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_schema_version_problem import (
    WorkflowSchemaVersionProblem,
)
from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
    WorkflowVersionCompatibilityCheck,
    WorkflowVersionCompatibilityIssue,
)

if TYPE_CHECKING:
    from griptape_nodes.node_library.workflow_registry import WorkflowMetadata


class SaveOnFailureArgumentAddition(WorkflowVersionCompatibilityCheck):
    """Check for workflow schema version compatibility due to missing --save-on-failure argument."""

    def applies_to_workflow(self, workflow_metadata: WorkflowMetadata) -> bool:
        try:
            workflow_version = semver.VersionInfo.parse(workflow_metadata.schema_version)
            return workflow_version < semver.VersionInfo(0, 18, 0)
        except Exception:
            return False

    def check_workflow(self, workflow_metadata: WorkflowMetadata) -> list[WorkflowVersionCompatibilityIssue]:
        issues = []

        try:
            workflow_schema_version = semver.VersionInfo.parse(workflow_metadata.schema_version)
        except Exception:
            return issues

        if workflow_schema_version < semver.VersionInfo(0, 18, 0):
            issues.append(
                WorkflowVersionCompatibilityIssue(
                    problem=WorkflowSchemaVersionProblem(
                        description=(
                            f"Schema version {workflow_metadata.schema_version} older than 0.18.0. "
                            "This workflow does not support --save-on-failure. Re-save to update."
                        )
                    ),
                    severity=WorkflowStatus.FLAWED,
                )
            )

        return issues
