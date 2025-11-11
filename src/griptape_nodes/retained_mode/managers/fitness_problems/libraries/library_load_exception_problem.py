from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class LibraryLoadExceptionProblem(LibraryProblem):
    """Problem indicating an exception occurred while loading the library file."""

    error_message: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[LibraryLoadExceptionProblem]) -> str:
        """Display library load exception problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "LibraryLoadExceptionProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one LibraryLoadExceptionProblem.",
                len(instances),
            )

        # Use the first instance's error message
        error_msg = instances[0].error_message
        return f"Exception occurred when attempting to load the library: {error_msg}."
