from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class DuplicateLibraryProblem(LibraryProblem):
    """Problem indicating a library with this name was already registered."""

    @classmethod
    def collate_problems_for_display(cls, instances: list[DuplicateLibraryProblem]) -> str:
        """Display duplicate library problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "DuplicateLibraryProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one DuplicateLibraryProblem.",
                len(instances),
            )

        return "Failed because a library with this name was already registered. Check the Settings to ensure duplicate libraries are not being loaded."
