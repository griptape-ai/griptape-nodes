from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem

logger = logging.getLogger(__name__)


@dataclass
class InvalidMetadataSchemaProblem(WorkflowProblem):
    """Problem indicating workflow metadata doesn't match required schema.

    This is one-time only - should only occur once per workflow.
    """

    section_path: str
    error_message: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[InvalidMetadataSchemaProblem]) -> str:
        """Display invalid metadata schema problem."""
        if len(instances) > 1:
            logger.error(
                "InvalidMetadataSchemaProblem received %d instances but should only receive 1. This indicates a logic error.",
                len(instances),
            )

        problem = instances[0]
        return f"'{problem.section_path}' metadata doesn't match schema: {problem.error_message}"
