from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem

logger = logging.getLogger(__name__)


@dataclass
class WorkflowNotFoundProblem(WorkflowProblem):
    """Problem indicating a workflow file could not be found.

    This is one-time only - should only occur once per workflow.
    """

    @classmethod
    def collate_problems_for_display(cls, instances: list[WorkflowNotFoundProblem]) -> str:
        """Display workflow not found problem."""
        if len(instances) > 1:
            logger.error(
                "WorkflowNotFoundProblem received %d instances but should only receive 1. This indicates a logic error.",
                len(instances),
            )

        return "Workflow file not found. Will be removed from configuration."
