from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem

logger = logging.getLogger(__name__)


@dataclass
class MissingLastModifiedDateProblem(WorkflowProblem):
    """Problem indicating workflow metadata is missing a last modified date.

    This is one-time only - should only occur once per workflow.
    """

    default_date: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[MissingLastModifiedDateProblem]) -> str:
        """Display missing last modified date problem."""
        if len(instances) > 1:
            logger.error(
                "MissingLastModifiedDateProblem received %d instances but should only receive 1. This indicates a logic error.",
                len(instances),
            )

        problem = instances[0]
        return f"Workflow metadata was missing a last modified date. Defaulting to {problem.default_date}. This value will be replaced with the current date the first time it is saved."
