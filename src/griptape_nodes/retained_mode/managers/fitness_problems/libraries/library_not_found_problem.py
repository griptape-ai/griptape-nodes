from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class LibraryNotFoundProblem(LibraryProblem):
    """Problem indicating a library file could not be found at the specified path."""

    library_path: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[LibraryNotFoundProblem]) -> str:
        """Display library not found problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "LibraryNotFoundProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one LibraryNotFoundProblem.",
                len(instances),
            )

        return "Library could not be found at the file path specified. It will be removed from the configuration."
