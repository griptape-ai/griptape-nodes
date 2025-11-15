from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem

logger = logging.getLogger(__name__)


@dataclass
class WorkflowSchemaVersionProblem(WorkflowProblem):
    """Problem indicating a workflow has schema version compatibility issues.

    This is context-specific and likely one-time only per workflow.
    """

    description: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[WorkflowSchemaVersionProblem]) -> str:
        """Display workflow schema version problems."""
        if len(instances) > 1:
            logger.error(
                "WorkflowSchemaVersionProblem received %d instances but should typically only receive 1. This may indicate multiple schema issues.",
                len(instances),
            )

        if len(instances) == 1:
            problem = instances[0]
            return problem.description

        # Multiple schema issues - list them
        output_lines = []
        output_lines.append(f"Encountered {len(instances)} workflow schema version issues:")
        for i, problem in enumerate(instances, 1):
            output_lines.append(f"  {i}. {problem.description}")

        return "\n".join(output_lines)
