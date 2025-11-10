from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.workflows.workflow_problem import WorkflowProblem

logger = logging.getLogger(__name__)


@dataclass
class InvalidTomlFormatProblem(WorkflowProblem):
    """Problem indicating workflow metadata is not valid TOML.

    This is one-time only - should only occur once per workflow.
    """

    error_message: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[InvalidTomlFormatProblem]) -> str:
        """Display invalid TOML format problem."""
        if len(instances) > 1:
            logger.error(
                "InvalidTomlFormatProblem received %d instances but should only receive 1. This indicates a logic error.",
                len(instances),
            )

        problem = instances[0]
        return f"Metadata not valid TOML: {problem.error_message}"
