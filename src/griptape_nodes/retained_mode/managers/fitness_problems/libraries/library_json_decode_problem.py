from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class LibraryJsonDecodeProblem(LibraryProblem):
    """Problem indicating a library file is not properly formatted JSON."""

    @classmethod
    def collate_problems_for_display(cls, instances: list[LibraryJsonDecodeProblem]) -> str:
        """Display library JSON decode problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "LibraryJsonDecodeProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one LibraryJsonDecodeProblem.",
                len(instances),
            )

        return "Library file not formatted as proper JSON."
