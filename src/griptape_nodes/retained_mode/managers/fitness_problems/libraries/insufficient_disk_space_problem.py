from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class InsufficientDiskSpaceProblem(LibraryProblem):
    """Problem indicating insufficient disk space for dependencies."""

    min_space_gb: float
    error_message: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[InsufficientDiskSpaceProblem]) -> str:
        """Display insufficient disk space problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "InsufficientDiskSpaceProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one InsufficientDiskSpaceProblem.",
                len(instances),
            )

        # Use the first instance's details
        problem = instances[0]
        return f"Insufficient disk space for dependencies (requires {problem.min_space_gb} GB): {problem.error_message}"
