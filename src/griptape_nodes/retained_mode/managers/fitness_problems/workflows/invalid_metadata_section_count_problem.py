from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem

logger = logging.getLogger(__name__)


@dataclass
class InvalidMetadataSectionCountProblem(WorkflowProblem):
    """Problem indicating workflow has wrong number of metadata sections.

    This is one-time only - should only occur once per workflow.
    """

    section_name: str
    count: int

    @classmethod
    def collate_problems_for_display(cls, instances: list[InvalidMetadataSectionCountProblem]) -> str:
        """Display invalid metadata section count problem."""
        if len(instances) > 1:
            logger.error(
                "InvalidMetadataSectionCountProblem received %d instances but should only receive 1. This indicates a logic error.",
                len(instances),
            )

        problem = instances[0]
        return f"Has {problem.count} '{problem.section_name}' sections. Expected exactly 1."
