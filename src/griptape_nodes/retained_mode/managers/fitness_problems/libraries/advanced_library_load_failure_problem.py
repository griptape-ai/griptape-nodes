from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class AdvancedLibraryLoadFailureProblem(LibraryProblem):
    """Problem indicating an advanced library module failed to load."""

    advanced_library_path: str
    error_message: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[AdvancedLibraryLoadFailureProblem]) -> str:
        """Display advanced library load failure problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "AdvancedLibraryLoadFailureProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one AdvancedLibraryLoadFailureProblem.",
                len(instances),
            )

        # Use the first instance's details
        problem = instances[0]
        return f"Failed to load Advanced Library module from '{problem.advanced_library_path}': {problem.error_message}"
