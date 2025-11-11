from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class VenvCreationFailedProblem(LibraryProblem):
    """Problem indicating virtual environment creation failed."""

    error_message: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[VenvCreationFailedProblem]) -> str:
        """Display venv creation failed problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "VenvCreationFailedProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one VenvCreationFailedProblem.",
                len(instances),
            )

        # Use the first instance's error message
        error_msg = instances[0].error_message
        return f"Failed to create virtual environment for library dependencies. Error: {error_msg}"
