"""Schema compatibility check for workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from griptape_nodes.retained_mode.griptape_nodes import Version
from griptape_nodes.retained_mode.managers.version_compatibility_manager import (
    WorkflowVersionCompatibilityCheck,
    WorkflowVersionCompatibilityIssue,
)
from griptape_nodes.retained_mode.managers.workflow_manager import WorkflowManager

if TYPE_CHECKING:
    from griptape_nodes.node_library.workflow_registry import WorkflowMetadata


class LocalExecutorArgumentAddition(WorkflowVersionCompatibilityCheck):
    """Check for workflow schema version compatibility issues due to missing `--json-input` argument in LocalExecutor."""

    def applies_to_workflow(self, workflow_metadata: WorkflowMetadata) -> bool:
        """Apply this check to workflows with schema version < 0.7.0."""
        workflow_version = Version.from_string(workflow_metadata.schema_version)
        return workflow_version is not None and workflow_version < Version(0, 7, 0)

    def check_workflow(self, workflow_metadata: WorkflowMetadata) -> list[WorkflowVersionCompatibilityIssue]:
        """Check workflow schema version compatibility."""
        issues = []

        workflow_schema_version = Version.from_string(workflow_metadata.schema_version)

        if workflow_schema_version is not None and workflow_schema_version < Version(0, 7, 0):
            issues.append(
                WorkflowVersionCompatibilityIssue(
                    message=f"Workflow schema version {workflow_metadata.schema_version} is older than version 0.7.0. "
                    "The generated LocalExecutor code for the workflow file is missing the `--json-input` argument, which may cause issues for Publish Workflow requests when using certain Library targets. "
                    "Consider updating the workflow by saving it again.",
                    severity=WorkflowManager.WorkflowStatus.FLAWED,
                )
            )

        return issues
