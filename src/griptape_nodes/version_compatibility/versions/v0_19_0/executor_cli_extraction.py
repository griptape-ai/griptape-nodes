"""Schema compatibility check for workflows that pre-date executor CLI extraction."""

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


class ExecutorCliExtraction(WorkflowVersionCompatibilityCheck):
    """Check for workflow schema version compatibility due to executor CLI extraction.

    Schema 0.19.0 moves executor-level CLI argument declarations off the generated
    workflow file's __main__ block and onto the WorkflowExecutor classes themselves.
    Workflows saved on earlier schemas still embed the old argparse boilerplate and
    won't pick up new executor-level flags until they are re-saved.
    """

    def applies_to_workflow(self, workflow_metadata: WorkflowMetadata) -> bool:
        try:
            workflow_version = semver.VersionInfo.parse(workflow_metadata.schema_version)
            return workflow_version < semver.VersionInfo(0, 19, 0)
        except Exception:
            return False

    def check_workflow(self, workflow_metadata: WorkflowMetadata) -> list[WorkflowVersionCompatibilityIssue]:
        issues = []

        try:
            workflow_schema_version = semver.VersionInfo.parse(workflow_metadata.schema_version)
        except Exception:
            return issues

        if workflow_schema_version < semver.VersionInfo(0, 19, 0):
            issues.append(
                WorkflowVersionCompatibilityIssue(
                    problem=WorkflowSchemaVersionProblem(
                        description=(
                            f"Schema version {workflow_metadata.schema_version} older than 0.19.0. "
                            "Executor-level CLI arguments are now owned by WorkflowExecutor classes; "
                            "re-save to delegate to the new entry point."
                        )
                    ),
                    severity=WorkflowStatus.FLAWED,
                )
            )

        return issues
