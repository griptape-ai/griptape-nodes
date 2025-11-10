from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class DependencyInstallationFailedProblem(LibraryProblem):
    """Problem indicating dependency installation failed."""

    error_details: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[DependencyInstallationFailedProblem]) -> str:
        """Display dependency installation failed problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "DependencyInstallationFailedProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one DependencyInstallationFailedProblem.",
                len(instances),
            )

        # Use the first instance's error details
        details = instances[0].error_details
        return f"Dependency installation failed: {details}"
