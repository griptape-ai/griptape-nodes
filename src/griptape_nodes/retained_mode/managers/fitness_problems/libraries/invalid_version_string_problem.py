from __future__ import annotations

import logging
from dataclasses import dataclass

from griptape_nodes.retained_mode.managers.fitness_problems.libraries.library_problem import LibraryProblem

logger = logging.getLogger(__name__)


@dataclass
class InvalidVersionStringProblem(LibraryProblem):
    """Problem indicating a library's version string is not valid (must be major.minor.patch format)."""

    version_string: str

    @classmethod
    def collate_problems_for_display(cls, instances: list[InvalidVersionStringProblem]) -> str:
        """Display invalid version string problem.

        There should only be one instance per library since each LibraryInfo
        is already associated with a specific library path.
        """
        if len(instances) > 1:
            logger.error(
                "InvalidVersionStringProblem: Expected 1 instance but got %s. Each LibraryInfo should only have one InvalidVersionStringProblem.",
                len(instances),
            )

        # Use the first instance's version string
        version = instances[0].version_string
        return f"Library's version string '{version}' wasn't valid. Must be in major.minor.patch format."
